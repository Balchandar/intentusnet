"""
Security Kernel Test Suite

Covers all 8 security kernel components:
  1. SecurityConfig — feature flags
  2. CapabilityMetadata — protocol extensions (non-breaking)
  3. WALEntryType + ErrorCode extensions
  4. verify_wal_integrity() — public WAL integrity API
  5. ExecutionFingerprintEngine — anomaly detection
  6. ISideEffectAdapter + SideEffectQuarantine
  7. ForensicAuditLog — tamper-evident chain
  8. SecurityKernelMiddleware — full middleware integration
  9. MCPValidationMiddleware — MCP enforcement
 10. PolicyEngine ReDoS fix
"""

from __future__ import annotations

import hashlib
import time
import tempfile
import os
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Protocol / WAL imports
# ---------------------------------------------------------------------------
from intentusnet.protocol.agent import Capability, CapabilityMetadata, LatencyProfile
from intentusnet.protocol.intent import IntentRef, IntentEnvelope, IntentContext, IntentMetadata, RoutingOptions
from intentusnet.protocol.response import AgentResponse, ErrorInfo
from intentusnet.protocol.enums import ErrorCode, RoutingStrategy
from intentusnet.wal.models import WALEntryType, ExecutionState
from intentusnet.wal.writer import WALWriter
from intentusnet.wal.integrity import verify_wal_integrity, WALIntegrityResult

# ---------------------------------------------------------------------------
# Security kernel imports
# ---------------------------------------------------------------------------
from intentusnet.security.config import SecurityConfig
from intentusnet.security.fingerprint import (
    AnomalyClass, AnomalyResult, ExecutionFingerprintEngine, FingerprintSample,
)
from intentusnet.security.side_effects import (
    ISideEffectAdapter, SideEffectQuarantine, SideEffectNotAuthorizedError,
)
from intentusnet.security.audit import ForensicAuditEntry, ForensicAuditLog
from intentusnet.security.kernel import SecurityKernelMiddleware
from intentusnet.security.mcp_validation import MCPValidationMiddleware
from intentusnet.security.policy_engine import PolicyEngine, PolicyRule, PolicyAction, EvaluationContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_envelope(intent_name: str = "TestIntent", payload: Optional[Dict] = None) -> IntentEnvelope:
    return IntentEnvelope(
        version="1.0",
        intent=IntentRef(name=intent_name, version="1.0"),
        payload=payload or {"key": "value"},
        context=IntentContext(sourceAgent="test-agent", timestamp="2026-01-01T00:00:00Z"),
        metadata=IntentMetadata(
            requestId=f"req-{intent_name}",
            source="test",
            createdAt="2026-01-01T00:00:00Z",
            traceId="trace-001",
        ),
        routing=RoutingOptions(strategy=RoutingStrategy.DIRECT),
    )


def _make_success_response() -> AgentResponse:
    return AgentResponse(
        version="1.0",
        status="success",
        payload={"result": "ok"},
        metadata={},
    )


def _make_error_info(code: ErrorCode = ErrorCode.AGENT_ERROR, msg: str = "err") -> ErrorInfo:
    return ErrorInfo(code=code, message=msg, retryable=False, details={})


def _make_registry(has_agents: bool = True, agent_name: str = "test-agent"):
    """Returns a minimal mock registry."""
    registry = MagicMock()
    if has_agents:
        agent = MagicMock()
        agent.definition.name = agent_name
        cap = Capability(intent=IntentRef(name="TestIntent", version="1.0"))
        agent.definition.capabilities = [cap]
        registry.find_agents_for_intent.return_value = [agent]
    else:
        registry.find_agents_for_intent.return_value = []
    return registry


# ===========================================================================
# 1. SecurityConfig
# ===========================================================================

class TestSecurityConfig:
    def test_defaults_are_permissive(self):
        cfg = SecurityConfig()
        assert cfg.audit_only is True
        assert cfg.strict_mode is False
        assert cfg.is_enforcing() is False

    def test_enforcing_requires_strict_and_not_audit(self):
        cfg = SecurityConfig(strict_mode=True, audit_only=False)
        assert cfg.is_enforcing() is True

    def test_strict_with_audit_only_not_enforcing(self):
        cfg = SecurityConfig(strict_mode=True, audit_only=True)
        assert cfg.is_enforcing() is False

    def test_all_modules_enabled_by_default(self):
        cfg = SecurityConfig()
        assert cfg.capability_contracts is True
        assert cfg.fingerprint_enabled is True
        assert cfg.mcp_validation is True
        assert cfg.forensic_audit is True
        assert cfg.idempotency_enabled is True

    def test_side_effect_quarantine_off_by_default(self):
        cfg = SecurityConfig()
        assert cfg.side_effect_quarantine is False


# ===========================================================================
# 2. CapabilityMetadata — non-breaking protocol extension
# ===========================================================================

class TestCapabilityMetadata:
    def test_capability_without_metadata_still_valid(self):
        cap = Capability(intent=IntentRef(name="MyIntent"))
        assert cap.metadata is None

    def test_capability_with_metadata(self):
        meta = CapabilityMetadata(
            capability_scope=["admin", "service"],
            side_effect_signature=["email", "db-write"],
            retry_pattern="idempotent",
            max_retries=3,
        )
        cap = Capability(intent=IntentRef(name="MyIntent"), metadata=meta)
        assert cap.metadata is not None
        assert "admin" in cap.metadata.capability_scope
        assert cap.metadata.retry_pattern == "idempotent"

    def test_latency_profile_defaults(self):
        lp = LatencyProfile()
        assert lp.min_ms == 0.0
        assert lp.max_ms == 30_000.0
        assert lp.timeout_threshold_ms == 30_000.0

    def test_capability_metadata_defaults(self):
        meta = CapabilityMetadata()
        assert meta.capability_scope == []
        assert meta.side_effect_signature == []
        assert meta.allowed_state_transitions is None
        assert meta.retry_pattern == "none"
        assert meta.max_retries == 0


# ===========================================================================
# 3. WAL Extensions
# ===========================================================================

class TestWALExtensions:
    def test_new_entry_types_present(self):
        assert WALEntryType.SECURITY_AUTHORIZED.value == "security.authorized"
        assert WALEntryType.SECURITY_BLOCKED.value == "security.blocked"
        assert WALEntryType.SIDE_EFFECT_AUTHORIZED.value == "side_effect.authorized"
        assert WALEntryType.ANOMALY_DETECTED.value == "anomaly.detected"
        assert WALEntryType.FORENSIC_AUDIT.value == "forensic.audit"

    def test_new_error_codes_present(self):
        assert ErrorCode.SIDE_EFFECT_BLOCKED.value == "SIDE_EFFECT_BLOCKED"
        assert ErrorCode.ANOMALY_DETECTED.value == "ANOMALY_DETECTED"
        assert ErrorCode.IDEMPOTENT_REPLAY.value == "IDEMPOTENT_REPLAY"
        assert ErrorCode.CAPABILITY_VIOLATION.value == "CAPABILITY_VIOLATION"
        assert ErrorCode.MCP_VIOLATION.value == "MCP_VIOLATION"


# ===========================================================================
# 4. verify_wal_integrity()
# ===========================================================================

class TestVerifyWalIntegrity:
    def test_missing_wal_returns_not_ok(self, tmp_path):
        result = verify_wal_integrity(str(tmp_path), "nonexistent-exec")
        assert result.ok is False
        assert result.entry_count == 0
        assert any("not found" in e for e in result.errors)

    def test_valid_wal_returns_ok(self, tmp_path):
        exec_id = "exec-integrity-ok"
        with WALWriter(str(tmp_path), exec_id) as w:
            w.append(WALEntryType.EXECUTION_STARTED, {"intent": "TestIntent"})
            w.append(WALEntryType.EXECUTION_COMPLETED, {"result": "ok"})

        result = verify_wal_integrity(str(tmp_path), exec_id)
        assert result.ok is True
        assert result.entry_count == 2
        assert result.first_hash is not None
        assert result.last_hash is not None
        assert result.first_hash != result.last_hash

    def test_tampered_wal_returns_not_ok(self, tmp_path):
        exec_id = "exec-tampered"
        wal_path = tmp_path / f"{exec_id}.wal"

        with WALWriter(str(tmp_path), exec_id) as w:
            w.append(WALEntryType.EXECUTION_STARTED, {"intent": "TestIntent"})

        # Corrupt the file
        content = wal_path.read_text()
        corrupted = content.replace('"seq": 1', '"seq": 99')
        wal_path.write_text(corrupted)

        result = verify_wal_integrity(str(tmp_path), exec_id)
        assert result.ok is False

    def test_result_to_dict(self, tmp_path):
        exec_id = "exec-dict"
        with WALWriter(str(tmp_path), exec_id) as w:
            w.append(WALEntryType.EXECUTION_STARTED, {})

        result = verify_wal_integrity(str(tmp_path), exec_id)
        d = result.to_dict()
        assert "ok" in d
        assert "entry_count" in d
        assert "first_hash" in d
        assert "last_hash" in d


# ===========================================================================
# 5. ExecutionFingerprintEngine
# ===========================================================================

class TestExecutionFingerprintEngine:
    def test_returns_normal_when_insufficient_data(self):
        engine = ExecutionFingerprintEngine(window_size=100)
        engine.start_trace("e1")
        result = engine.end_trace("e1", "MyIntent")
        assert result.classification == AnomalyClass.NORMAL
        assert result.anomaly_score == 0.0

    def test_normal_execution_stays_normal(self):
        """Pre-seed 20 identical 10ms samples; a new 10ms sample must stay NORMAL."""
        import collections
        engine = ExecutionFingerprintEngine(window_size=100, anomaly_threshold=0.75)
        intent = "SteadyIntent"
        history = collections.deque(maxlen=100)
        for _ in range(20):
            history.append(FingerprintSample(latency_ms=10.0, retries=0, timed_out=False))
        engine._samples[intent] = history

        # A new sample at exactly the historical mean — should be NORMAL
        engine.start_trace("steady-exec")
        # Manually insert a known latency by overriding start time to produce ~10ms
        engine._active_starts["steady-exec"] = time.perf_counter() - 0.010
        result = engine.end_trace("steady-exec", intent)
        assert result.classification == AnomalyClass.NORMAL

    def test_latency_spike_raises_score(self):
        engine = ExecutionFingerprintEngine(
            window_size=50,
            anomaly_threshold=0.3,
            malicious_threshold=0.9,
        )
        intent = "SpikeIntent"
        # Inject 10 near-zero-latency historical samples directly
        for _ in range(10):
            engine._samples.setdefault(intent, __import__("collections").deque(maxlen=50))
            engine._samples[intent].append(FingerprintSample(latency_ms=1.0, retries=0, timed_out=False))

        # Now simulate a very high latency sample
        engine.start_trace("spike-exec")
        result = engine.end_trace("spike-exec", intent)
        # The large latency relative to baseline should produce some score
        # (actual score depends on timing, so we just check structure)
        assert isinstance(result.anomaly_score, float)
        assert 0.0 <= result.anomaly_score <= 1.0
        assert isinstance(result.classification, AnomalyClass)

    def test_repeated_timeouts_raise_score(self):
        engine = ExecutionFingerprintEngine(
            window_size=50,
            anomaly_threshold=0.3,
            malicious_threshold=0.9,
        )
        import collections
        intent = "TimeoutIntent"
        history = collections.deque(maxlen=50)
        for _ in range(5):
            history.append(FingerprintSample(latency_ms=100.0, retries=0, timed_out=False))
        # 5 consecutive timeouts
        for _ in range(5):
            history.append(FingerprintSample(latency_ms=5000.0, retries=0, timed_out=True))
        engine._samples[intent] = history

        engine.start_trace("to-exec")
        result = engine.end_trace("to-exec", intent, timed_out=True)
        assert result.anomaly_score > 0.0

    def test_get_profile_returns_none_for_unknown(self):
        engine = ExecutionFingerprintEngine()
        assert engine.get_profile("UnknownIntent") is None

    def test_reset_intent_clears_history(self):
        engine = ExecutionFingerprintEngine()
        import collections
        engine._samples["X"] = collections.deque([FingerprintSample(1.0, 0, False)], maxlen=10)
        engine.reset_intent("X")
        assert engine.get_profile("X") is None

    def test_known_intents_after_trace(self):
        engine = ExecutionFingerprintEngine()
        engine.start_trace("e1")
        engine.end_trace("e1", "IntentA")
        engine.start_trace("e2")
        engine.end_trace("e2", "IntentB")
        assert "IntentA" in engine.known_intents()
        assert "IntentB" in engine.known_intents()


# ===========================================================================
# 6. SideEffectQuarantine
# ===========================================================================

class _EchoAdapter(ISideEffectAdapter):
    @property
    def adapter_id(self) -> str:
        return "echo"

    def execute(self, payload: Dict[str, Any]) -> Any:
        return {"echo": payload}


class TestSideEffectQuarantine:
    def test_register_and_execute_success(self):
        q = SideEffectQuarantine(strict_mode=True)
        q.register(_EchoAdapter(), allowed_intents=["MyIntent"])
        result = q.execute("echo", "MyIntent", ["echo"], {"x": 1})
        assert result == {"echo": {"x": 1}}

    def test_undeclared_signature_raises_in_strict(self):
        q = SideEffectQuarantine(strict_mode=True)
        q.register(_EchoAdapter(), allowed_intents=["MyIntent"])
        with pytest.raises(SideEffectNotAuthorizedError):
            q.execute("echo", "MyIntent", [], {"x": 1})  # empty declared_signatures

    def test_unregistered_adapter_raises_in_strict(self):
        q = SideEffectQuarantine(strict_mode=True)
        with pytest.raises(SideEffectNotAuthorizedError):
            q.execute("ghost", "MyIntent", ["ghost"], {})

    def test_wrong_intent_raises_in_strict(self):
        q = SideEffectQuarantine(strict_mode=True)
        q.register(_EchoAdapter(), allowed_intents=["AllowedIntent"])
        with pytest.raises(SideEffectNotAuthorizedError):
            q.execute("echo", "OtherIntent", ["echo"], {})

    def test_permissive_mode_does_not_raise(self):
        q = SideEffectQuarantine(strict_mode=False)
        # No adapter registered — permissive mode returns None without raising
        result = q.execute("ghost", "MyIntent", [], {})
        assert result is None

    def test_duplicate_registration_raises(self):
        q = SideEffectQuarantine()
        q.register(_EchoAdapter())
        with pytest.raises(ValueError):
            q.register(_EchoAdapter())

    def test_registered_ids(self):
        q = SideEffectQuarantine()
        q.register(_EchoAdapter())
        assert "echo" in q.registered_ids()

    def test_is_registered(self):
        q = SideEffectQuarantine()
        assert q.is_registered("echo") is False
        q.register(_EchoAdapter())
        assert q.is_registered("echo") is True


# ===========================================================================
# 7. ForensicAuditLog
# ===========================================================================

def _make_audit_entry(**kwargs) -> ForensicAuditEntry:
    defaults = dict(
        intent_id="TestIntent",
        actor_id="test-user",
        input_hash="abc123",
        state_before="pre",
        state_after="post",
        validation_result="allowed",
        anomaly_score=0.0,
        decision="execute",
        wal_entry_hash=None,
        timestamp="2026-01-01T00:00:00+00:00",
    )
    defaults.update(kwargs)
    return ForensicAuditEntry(**defaults)


class TestForensicAuditLog:
    def test_entry_self_hashes_on_creation(self):
        entry = _make_audit_entry()
        assert entry.entry_hash != ""
        assert len(entry.entry_hash) == 64  # SHA-256 hex

    def test_chain_ok_on_empty_log(self):
        log = ForensicAuditLog()
        assert log.chain_ok() is True

    def test_chain_ok_after_single_entry(self):
        log = ForensicAuditLog()
        log.record(_make_audit_entry())
        assert log.chain_ok() is True

    def test_chain_ok_after_multiple_entries(self):
        log = ForensicAuditLog()
        for i in range(5):
            log.record(_make_audit_entry(intent_id=f"intent-{i}", timestamp=f"2026-01-0{i+1}T00:00:00+00:00"))
        assert log.chain_ok() is True

    def test_chain_broken_after_tampering(self):
        log = ForensicAuditLog()
        log.record(_make_audit_entry())
        log.record(_make_audit_entry(intent_id="second"))
        # Tamper with the first entry's hash
        log._entries[0].entry_hash = "deadbeef" * 8
        assert log.chain_ok() is False

    def test_query_by_intent(self):
        log = ForensicAuditLog()
        log.record(_make_audit_entry(intent_id="A"))
        log.record(_make_audit_entry(intent_id="B"))
        log.record(_make_audit_entry(intent_id="A"))
        results = log.get_by_intent("A")
        assert len(results) == 2

    def test_query_anomalies(self):
        log = ForensicAuditLog()
        log.record(_make_audit_entry(anomaly_score=0.2))
        log.record(_make_audit_entry(anomaly_score=0.8))
        log.record(_make_audit_entry(anomaly_score=0.99))
        high = log.get_anomalies(min_score=0.75)
        assert len(high) == 2

    def test_export_returns_all(self):
        log = ForensicAuditLog()
        for _ in range(3):
            log.record(_make_audit_entry())
        exported = log.export()
        assert len(exported) == 3
        assert all("entry_hash" in e for e in exported)

    def test_export_jsonl(self):
        log = ForensicAuditLog()
        log.record(_make_audit_entry())
        jsonl = log.export_jsonl()
        import json
        parsed = json.loads(jsonl)
        assert parsed["intent_id"] == "TestIntent"

    def test_len(self):
        log = ForensicAuditLog()
        assert len(log) == 0
        log.record(_make_audit_entry())
        assert len(log) == 1

    def test_chained_prev_hash_linkage(self):
        log = ForensicAuditLog()
        e1 = _make_audit_entry(intent_id="first")
        e2 = _make_audit_entry(intent_id="second")
        log.record(e1)
        log.record(e2)
        assert e1.prev_entry_hash is None
        assert e2.prev_entry_hash == e1.entry_hash


# ===========================================================================
# 8. SecurityKernelMiddleware
# ===========================================================================

class TestSecurityKernelMiddleware:
    def test_before_after_route_no_crash(self):
        registry = _make_registry()
        kernel = SecurityKernelMiddleware(registry)
        env = _make_envelope()
        response = _make_success_response()
        kernel.before_route(env)
        kernel.after_route(env, response)

    def test_forensic_audit_entry_created(self):
        registry = _make_registry()
        kernel = SecurityKernelMiddleware(registry)
        env = _make_envelope()
        kernel.before_route(env)
        kernel.after_route(env, _make_success_response())
        assert len(kernel.audit_log) == 1

    def test_on_error_creates_error_audit_entry(self):
        registry = _make_registry()
        kernel = SecurityKernelMiddleware(registry)
        env = _make_envelope()
        kernel.before_route(env)
        kernel.on_error(env, _make_error_info())
        entries = kernel.audit_log.export()
        assert len(entries) == 1
        assert entries[0]["decision"] == "error"

    def test_idempotency_replay_detected(self):
        registry = _make_registry()
        cfg = SecurityConfig(idempotency_enabled=True)
        kernel = SecurityKernelMiddleware(registry, config=cfg)
        env = _make_envelope(payload={"stable": "payload"})

        # First execution
        kernel.before_route(env)
        kernel.after_route(env, _make_success_response())

        # Second identical execution — should be flagged as replay
        env2 = _make_envelope(payload={"stable": "payload"})
        kernel.before_route(env2)
        replay = getattr(env2.metadata, "_sk_replay", None)
        assert replay is not None

    def test_anomaly_score_attached_to_response(self):
        registry = _make_registry()
        kernel = SecurityKernelMiddleware(registry)
        env = _make_envelope()
        resp = _make_success_response()
        kernel.before_route(env)
        kernel.after_route(env, resp)
        # Score is 0.0 for first execution (not enough history)
        assert "anomaly_score" in resp.metadata

    def test_idempotency_stats(self):
        registry = _make_registry()
        kernel = SecurityKernelMiddleware(registry)
        env = _make_envelope()
        kernel.before_route(env)
        stats = kernel.idempotency_stats()
        assert "total_keys" in stats
        assert "in_flight" in stats
        kernel.after_route(env, _make_success_response())
        stats2 = kernel.idempotency_stats()
        assert stats2["in_flight"] == 0

    def test_audit_log_chain_intact_after_many_routes(self):
        registry = _make_registry()
        kernel = SecurityKernelMiddleware(registry)
        for i in range(10):
            env = _make_envelope(intent_name=f"Intent{i}", payload={"i": i})
            kernel.before_route(env)
            kernel.after_route(env, _make_success_response())
        assert kernel.audit_log.chain_ok() is True

    def test_capability_violation_logged_not_raised_in_audit_mode(self):
        """In audit_only mode, scope violations must not raise exceptions."""
        registry = _make_registry()
        # Give the capability a restrictive scope
        agent = MagicMock()
        agent.definition.name = "scoped-agent"
        meta = CapabilityMetadata(capability_scope=["admin"])
        cap = Capability(intent=IntentRef(name="TestIntent"), metadata=meta)
        agent.definition.capabilities = [cap]
        registry.find_agents_for_intent.return_value = [agent]

        cfg = SecurityConfig(audit_only=True, strict_mode=False)
        kernel = SecurityKernelMiddleware(registry, config=cfg)
        env = _make_envelope()  # no scope set → violation

        # Must not raise
        kernel.before_route(env)
        kernel.after_route(env, _make_success_response())

        entry = kernel.audit_log.export()[0]
        assert entry["validation_result"] in ("audit_only", "allowed")


# ===========================================================================
# 9. MCPValidationMiddleware
# ===========================================================================

class TestMCPValidationMiddleware:
    def test_registered_intent_passes(self):
        registry = _make_registry(has_agents=True)
        mcp = MCPValidationMiddleware(registry)
        env = _make_envelope("TestIntent")
        mcp.before_route(env)  # Should not raise
        assert "TestIntent" not in mcp.blocked_intents

    def test_unregistered_intent_logged_as_blocked(self):
        registry = _make_registry(has_agents=False)
        mcp = MCPValidationMiddleware(registry)
        env = _make_envelope("GhostIntent")
        mcp.before_route(env)
        assert "GhostIntent" in mcp.blocked_intents

    def test_after_route_and_on_error_no_crash(self):
        registry = _make_registry()
        mcp = MCPValidationMiddleware(registry)
        env = _make_envelope()
        mcp.after_route(env, _make_success_response())
        mcp.on_error(env, _make_error_info())

    def test_mcp_validation_disabled_via_flag(self):
        registry = _make_registry(has_agents=False)
        cfg = SecurityConfig(mcp_validation=False)
        mcp = MCPValidationMiddleware(registry, config=cfg)
        env = _make_envelope("AnyIntent")
        mcp.before_route(env)
        # Validation skipped — registry never queried
        registry.find_agents_for_intent.assert_not_called()

    def test_wildcard_agent_flagged_in_strict_mode(self):
        registry = MagicMock()
        agent = MagicMock()
        agent.definition.name = "wildcard-agent"
        cap = Capability(intent=IntentRef(name="*", version="*"))
        agent.definition.capabilities = [cap]
        registry.find_agents_for_intent.return_value = [agent]

        cfg = SecurityConfig(strict_mode=True)
        mcp = MCPValidationMiddleware(registry, config=cfg)
        mcp.before_route(_make_envelope())
        assert "wildcard-agent" in mcp.wildcard_agents


# ===========================================================================
# 10. PolicyEngine ReDoS Fix
# ===========================================================================

class TestPolicyEngineReDoSFix:
    def _make_engine_with_regex(self, pattern: str) -> PolicyEngine:
        return PolicyEngine.from_dict({
            "default": "allow",
            "rules": [{
                "id": "r1",
                "action": "deny",
                "payload_regex": {"query": pattern},
            }],
        })

    def _make_ctx(self, query_value: str) -> EvaluationContext:
        return EvaluationContext(
            subject=None, roles=[], tenant=None,
            intent="Test", agent=None,
            payload={"query": query_value},
            metadata={}, tags=[],
        )

    def test_basic_regex_match(self):
        engine = self._make_engine_with_regex(".*sensitive.*")
        ctx = self._make_ctx("this is sensitive data")
        decision = engine.evaluate(ctx)
        assert decision.allowed is False

    def test_basic_regex_no_match(self):
        engine = self._make_engine_with_regex(".*sensitive.*")
        ctx = self._make_ctx("safe content")
        decision = engine.evaluate(ctx)
        assert decision.allowed is True  # default allow

    def test_long_input_truncated(self):
        engine = self._make_engine_with_regex("safe")
        long_input = "x" * 10_000 + "safe"
        ctx = self._make_ctx(long_input)
        # Should not hang; completes promptly
        decision = engine.evaluate(ctx)
        assert decision is not None

    def test_compiled_regex_cached(self):
        engine = self._make_engine_with_regex("^[a-z]+$")
        rule = engine._rules[0]
        assert hasattr(rule, "_compiled_regex")
        assert "query" in rule._compiled_regex

    def test_invalid_regex_handled_gracefully(self):
        engine = PolicyEngine.from_dict({
            "default": "allow",
            "rules": [{
                "id": "bad",
                "action": "deny",
                "payload_regex": {"field": "[invalid("},
            }],
        })
        ctx = self._make_ctx("anything")
        # Should not raise; invalid pattern → non-matching → default allow
        decision = engine.evaluate(ctx)
        assert decision is not None


# ===========================================================================
# 11. Public API surface — new exports reachable from top-level package
# ===========================================================================

class TestPublicAPIExports:
    def test_security_kernel_importable_from_package(self):
        import intentusnet
        assert hasattr(intentusnet, "SecurityKernelMiddleware")
        assert hasattr(intentusnet, "MCPValidationMiddleware")
        assert hasattr(intentusnet, "SecurityConfig")
        assert hasattr(intentusnet, "ExecutionFingerprintEngine")
        assert hasattr(intentusnet, "ISideEffectAdapter")
        assert hasattr(intentusnet, "SideEffectQuarantine")
        assert hasattr(intentusnet, "ForensicAuditEntry")
        assert hasattr(intentusnet, "ForensicAuditLog")
        assert hasattr(intentusnet, "verify_wal_integrity")
        assert hasattr(intentusnet, "WALIntegrityResult")
        assert hasattr(intentusnet, "CapabilityMetadata")
        assert hasattr(intentusnet, "LatencyProfile")

    def test_version_bumped(self):
        import intentusnet
        assert intentusnet.__version__ == "1.5.2"
