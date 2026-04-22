"""
Security Kernel v2.1 — Phase 8 Tests

Covers SecurityKernelV2:
  - Initialisation: all v2 components created from config flags
  - before_route: backpressure FAIL_SAFE gate, circuit-breaker gate,
    capability-governor gate, EXECUTION_STARTED event, causality registration
  - after_route: circuit-breaker record, backpressure update,
    EXECUTION_COMPLETED event
  - on_error: circuit-breaker failure, EXECUTION_FAILED event
  - check_allowed(): synchronous permit check
  - v2_stats() observability
  - Property accessors (event_bus, circuit_breaker, …)
  - Backward compatibility: v1 behaviour unchanged when all v2 flags off
  - Enforcement vs audit_only metadata markers
  - Thread safety: parallel before_route/after_route calls
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

from intentusnet.protocol.agent import Capability
from intentusnet.protocol.intent import (
    IntentEnvelope, IntentRef, IntentContext, IntentMetadata, RoutingOptions,
)
from intentusnet.protocol.response import AgentResponse, ErrorInfo
from intentusnet.protocol.enums import ErrorCode, RoutingStrategy

from intentusnet.security.kernel_v2 import SecurityKernelV2, _SK_V2_BLOCKED
from intentusnet.security.config import SecurityConfig
from intentusnet.security.circuit_breaker_v2 import CircuitBreaker, CircuitState
from intentusnet.security.capability_governor_v2 import CapabilityGovernor
from intentusnet.security.backpressure import BackpressureManager, BackpressureMetrics
from intentusnet.security.fingerprint_v2 import AdaptiveFingerprintEngineV2
from intentusnet.security.causality_index import CausalityIndex
from intentusnet.security.event_bus import SecurityEventBus, SecurityEventType
from intentusnet.security.types import DegradationState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env(intent: str = "test.intent", request_id: str = "req-1") -> IntentEnvelope:
    return IntentEnvelope(
        version="1.0",
        intent=IntentRef(name=intent, version="1.0"),
        payload={"k": "v"},
        context=IntentContext(sourceAgent="tester", timestamp="2026-01-01T00:00:00Z"),
        metadata=IntentMetadata(
            requestId=request_id,
            source="test",
            createdAt="2026-01-01T00:00:00Z",
            traceId="t1",
        ),
        routing=RoutingOptions(strategy=RoutingStrategy.DIRECT),
    )


def _ok_response() -> AgentResponse:
    return AgentResponse(
        version="1.0", status="success",
        payload={"result": "ok"}, metadata={},
    )


def _err_response() -> AgentResponse:
    return AgentResponse(
        version="1.0", status="error",
        payload={}, metadata={},
        error=ErrorInfo(code=ErrorCode.AGENT_ERROR, message="boom",
                        retryable=False, details={}),
    )


def _registry():
    r = MagicMock()
    agent = MagicMock()
    agent.definition.name = "test-agent"
    cap = Capability(intent=IntentRef(name="test.intent", version="1.0"))
    agent.definition.capabilities = [cap]
    r.find_agents_for_intent.return_value = [agent]
    return r


def _drain(bus: SecurityEventBus, timeout: float = 0.5) -> None:
    deadline = time.time() + timeout
    while bus.queue_depth > 0 and time.time() < deadline:
        time.sleep(0.01)


def _kernel_all_off(**kwargs) -> SecurityKernelV2:
    """Kernel with all v2 flags off — pure v1 behaviour."""
    cfg = SecurityConfig(fingerprint_enabled=False, forensic_audit=False,
                         idempotency_enabled=False)
    return SecurityKernelV2(_registry(), cfg, **kwargs)


def _kernel_all_on(bus: Optional[SecurityEventBus] = None) -> SecurityKernelV2:
    """Kernel with all v2 flags on."""
    cfg = SecurityConfig(
        fingerprint_enabled=False,
        forensic_audit=False,
        idempotency_enabled=False,
        security_trace_enabled=True,
        circuit_breaker_enabled=True,
        circuit_breaker_failure_threshold=3,
        capability_governor_enabled=True,
        backpressure_enabled=True,
        adaptive_fingerprint=True,
        causality_tracking_enabled=True,
    )
    return SecurityKernelV2(_registry(), cfg, event_bus=bus)


# ===========================================================================
# Initialisation — v2 components created from config
# ===========================================================================

class TestSecurityKernelV2Init:
    def test_all_off_no_v2_components(self):
        k = _kernel_all_off()
        assert k.circuit_breaker is None
        assert k.capability_governor is None
        assert k.backpressure_manager is None
        assert k.adaptive_fingerprint is None
        assert k.causality is None
        assert k.event_bus is None

    def test_circuit_breaker_created_from_flag(self):
        cfg = SecurityConfig(circuit_breaker_enabled=True,
                             fingerprint_enabled=False,
                             forensic_audit=False,
                             idempotency_enabled=False)
        k = SecurityKernelV2(_registry(), cfg)
        assert isinstance(k.circuit_breaker, CircuitBreaker)

    def test_capability_governor_created_from_flag(self):
        cfg = SecurityConfig(capability_governor_enabled=True,
                             fingerprint_enabled=False,
                             forensic_audit=False,
                             idempotency_enabled=False)
        k = SecurityKernelV2(_registry(), cfg)
        assert isinstance(k.capability_governor, CapabilityGovernor)

    def test_backpressure_created_from_flag(self):
        cfg = SecurityConfig(backpressure_enabled=True,
                             fingerprint_enabled=False,
                             forensic_audit=False,
                             idempotency_enabled=False)
        k = SecurityKernelV2(_registry(), cfg)
        assert isinstance(k.backpressure_manager, BackpressureManager)

    def test_adaptive_fingerprint_created_from_flag(self):
        cfg = SecurityConfig(adaptive_fingerprint=True,
                             fingerprint_enabled=False,
                             forensic_audit=False,
                             idempotency_enabled=False)
        k = SecurityKernelV2(_registry(), cfg)
        assert isinstance(k.adaptive_fingerprint, AdaptiveFingerprintEngineV2)

    def test_causality_created_from_flag(self):
        cfg = SecurityConfig(causality_tracking_enabled=True,
                             fingerprint_enabled=False,
                             forensic_audit=False,
                             idempotency_enabled=False)
        k = SecurityKernelV2(_registry(), cfg)
        assert isinstance(k.causality, CausalityIndex)

    def test_event_bus_created_from_flag(self):
        cfg = SecurityConfig(security_trace_enabled=True,
                             fingerprint_enabled=False,
                             forensic_audit=False,
                             idempotency_enabled=False)
        k = SecurityKernelV2(_registry(), cfg)
        assert isinstance(k.event_bus, SecurityEventBus)

    def test_injected_components_used(self):
        bus = SecurityEventBus()
        cb  = CircuitBreaker()
        gov = CapabilityGovernor()
        k = SecurityKernelV2(
            _registry(),
            event_bus=bus, circuit_breaker=cb, capability_governor=gov,
        )
        assert k.event_bus is bus
        assert k.circuit_breaker is cb
        assert k.capability_governor is gov

    def test_default_config_used_when_none(self):
        k = SecurityKernelV2(_registry())
        assert k.config is not None


# ===========================================================================
# before_route — backpressure gate
# ===========================================================================

class TestBeforeRouteBackpressure:
    def _bp_in_fail_safe(self) -> BackpressureManager:
        bp = BackpressureManager(
            fail_safe_thresholds=(1, 0, 0),
            hysteresis_seconds=0,
        )
        bp.update(BackpressureMetrics(event_bus_lag=2))
        assert bp.current_state == DegradationState.FAIL_SAFE
        return bp

    def test_fail_safe_sets_blocked_marker_audit_only(self):
        bp = self._bp_in_fail_safe()
        k = SecurityKernelV2(
            _registry(), backpressure_manager=bp,
        )
        env = _env()
        k.before_route(env)
        assert getattr(env.metadata, _SK_V2_BLOCKED, None) is not None

    def test_normal_state_does_not_block(self):
        bp = BackpressureManager()
        k = SecurityKernelV2(_registry(), backpressure_manager=bp)
        env = _env()
        k.before_route(env)
        assert getattr(env.metadata, _SK_V2_BLOCKED, None) is None


# ===========================================================================
# before_route — circuit breaker gate
# ===========================================================================

class TestBeforeRouteCircuitBreaker:
    def test_open_circuit_sets_blocked_marker(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record("test.intent", None, success=False)
        assert cb.get_state("test.intent") == CircuitState.OPEN
        k = SecurityKernelV2(_registry(), circuit_breaker=cb)
        env = _env(intent="test.intent")
        k.before_route(env)
        assert getattr(env.metadata, _SK_V2_BLOCKED, None) is not None

    def test_closed_circuit_does_not_block(self):
        cb = CircuitBreaker(failure_threshold=10)
        k = SecurityKernelV2(_registry(), circuit_breaker=cb)
        env = _env(intent="test.intent")
        k.before_route(env)
        assert getattr(env.metadata, _SK_V2_BLOCKED, None) is None

    def test_half_open_probe_allowed(self):
        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0.05)
        cb.record("test.intent", None, success=False)
        time.sleep(0.1)
        k = SecurityKernelV2(_registry(), circuit_breaker=cb)
        env = _env(intent="test.intent")
        k.before_route(env)
        # HALF_OPEN probe: first allow() returns True → no block
        assert getattr(env.metadata, _SK_V2_BLOCKED, None) is None


# ===========================================================================
# before_route — capability governor gate
# ===========================================================================

class TestBeforeRouteCapabilityGovernor:
    def test_suspended_intent_sets_blocked_marker(self):
        gov = CapabilityGovernor()
        gov.suspend("test.intent")
        k = SecurityKernelV2(_registry(), capability_governor=gov)
        env = _env(intent="test.intent")
        k.before_route(env)
        assert getattr(env.metadata, _SK_V2_BLOCKED, None) is not None

    def test_allowed_intent_does_not_block(self):
        gov = CapabilityGovernor()
        k = SecurityKernelV2(_registry(), capability_governor=gov)
        env = _env(intent="test.intent")
        k.before_route(env)
        assert getattr(env.metadata, _SK_V2_BLOCKED, None) is None


# ===========================================================================
# before_route — causality registration
# ===========================================================================

class TestBeforeRouteCausality:
    def test_execution_registered(self):
        causality = CausalityIndex()
        k = SecurityKernelV2(_registry(), causality_index=causality)
        env = _env(intent="test.intent", request_id="exec-99")
        k.before_route(env)
        node = causality.get_node("exec-99")
        assert node is not None
        assert node.metadata.get("intent_name") == "test.intent"


# ===========================================================================
# before_route — EXECUTION_STARTED event
# ===========================================================================

class TestBeforeRouteEvents:
    def test_execution_started_emitted(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.EXECUTION_STARTED})
        k = SecurityKernelV2(_registry(), event_bus=bus)
        env = _env(intent="test.intent")
        try:
            k.before_route(env)
            _drain(bus)
            assert any(e.event_type == SecurityEventType.EXECUTION_STARTED
                       for e in events)
        finally:
            bus.stop()

    def test_no_started_event_when_blocked(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.EXECUTION_STARTED})
        cb = CircuitBreaker(failure_threshold=1)
        cb.record("test.intent", None, success=False)
        k = SecurityKernelV2(_registry(), circuit_breaker=cb, event_bus=bus)
        env = _env(intent="test.intent")
        try:
            k.before_route(env)
            _drain(bus)
            started = [e for e in events
                       if e.event_type == SecurityEventType.EXECUTION_STARTED]
            assert started == []
        finally:
            bus.stop()


# ===========================================================================
# after_route — circuit breaker update
# ===========================================================================

class TestAfterRouteCircuitBreaker:
    def test_success_records_as_success(self):
        cb = CircuitBreaker(failure_threshold=3)
        k = SecurityKernelV2(_registry(), circuit_breaker=cb)
        env = _env()
        k.before_route(env)
        k.after_route(env, _ok_response())
        # 0 failures → still CLOSED
        assert cb.get_state("test.intent") == CircuitState.CLOSED

    def test_error_response_records_as_failure(self):
        cb = CircuitBreaker(failure_threshold=1)
        k = SecurityKernelV2(_registry(), circuit_breaker=cb)
        env = _env()
        k.before_route(env)
        k.after_route(env, _err_response())
        assert cb.get_state("test.intent") == CircuitState.OPEN


# ===========================================================================
# after_route — EXECUTION_COMPLETED event
# ===========================================================================

class TestAfterRouteEvents:
    def test_completed_event_emitted(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.EXECUTION_COMPLETED})
        k = SecurityKernelV2(_registry(), event_bus=bus)
        env = _env()
        try:
            k.before_route(env)
            k.after_route(env, _ok_response())
            _drain(bus)
            assert any(e.event_type == SecurityEventType.EXECUTION_COMPLETED
                       for e in events)
        finally:
            bus.stop()

    def test_completed_payload_has_success_flag(self):
        bus = SecurityEventBus()
        completed = []
        bus.subscribe("t", lambda e: completed.append(e),
                      {SecurityEventType.EXECUTION_COMPLETED})
        k = SecurityKernelV2(_registry(), event_bus=bus)
        env = _env()
        try:
            k.before_route(env)
            k.after_route(env, _ok_response())
            _drain(bus)
            assert completed[0].payload["success"] is True
        finally:
            bus.stop()


# ===========================================================================
# after_route — backpressure update
# ===========================================================================

class TestAfterRouteBackpressure:
    def test_backpressure_updated_after_route(self):
        bp = BackpressureManager(hysteresis_seconds=0)
        k = SecurityKernelV2(_registry(), backpressure_manager=bp)
        env = _env()
        k.before_route(env)
        k.after_route(env, _ok_response())
        # No assertion on state change — just verify it doesn't raise
        assert bp.current_state is not None


# ===========================================================================
# on_error — circuit breaker + events
# ===========================================================================

class TestOnError:
    def test_on_error_records_failure_to_circuit_breaker(self):
        cb = CircuitBreaker(failure_threshold=1)
        k = SecurityKernelV2(_registry(), circuit_breaker=cb)
        env = _env()
        k.before_route(env)
        k.on_error(env, ErrorInfo(code=ErrorCode.AGENT_ERROR, message="x",
                                   retryable=False, details={}))
        assert cb.get_state("test.intent") == CircuitState.OPEN

    def test_on_error_emits_failed_event(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.EXECUTION_FAILED})
        k = SecurityKernelV2(_registry(), event_bus=bus)
        env = _env()
        try:
            k.before_route(env)
            k.on_error(env, ErrorInfo(code=ErrorCode.AGENT_ERROR, message="err",
                                       retryable=False, details={}))
            _drain(bus)
            assert any(e.event_type == SecurityEventType.EXECUTION_FAILED
                       for e in events)
        finally:
            bus.stop()


# ===========================================================================
# check_allowed()
# ===========================================================================

class TestCheckAllowed:
    def test_allowed_when_nothing_active(self):
        k = _kernel_all_off()
        ok, reason = k.check_allowed("any.intent")
        assert ok is True
        assert reason == ""

    def test_blocked_by_open_circuit(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record("blocked.intent", None, success=False)
        k = SecurityKernelV2(_registry(), circuit_breaker=cb)
        ok, reason = k.check_allowed("blocked.intent")
        assert ok is False
        assert "circuit" in reason.lower()

    def test_blocked_by_suspended_intent(self):
        gov = CapabilityGovernor()
        gov.suspend("locked.intent")
        k = SecurityKernelV2(_registry(), capability_governor=gov)
        ok, reason = k.check_allowed("locked.intent")
        assert ok is False
        assert "governor" in reason.lower()

    def test_blocked_by_fail_safe(self):
        bp = BackpressureManager(
            fail_safe_thresholds=(1, 0, 0),
            hysteresis_seconds=0,
        )
        bp.update(BackpressureMetrics(event_bus_lag=2))
        k = SecurityKernelV2(_registry(), backpressure_manager=bp)
        ok, reason = k.check_allowed("any.intent")
        assert ok is False
        assert "fail_safe" in reason.lower()

    def test_check_does_not_mutate_circuit(self):
        cb = CircuitBreaker(failure_threshold=10)
        k = SecurityKernelV2(_registry(), circuit_breaker=cb)
        # check_allowed should NOT consume the HALF_OPEN probe
        k.check_allowed("test.intent")
        k.check_allowed("test.intent")
        # circuit not affected
        assert cb.get_state("test.intent") == CircuitState.CLOSED


# ===========================================================================
# v2_stats()
# ===========================================================================

class TestV2Stats:
    def test_stats_when_all_off(self):
        k = _kernel_all_off()
        s = k.v2_stats()
        assert s["circuit_breaker_enabled"] is False
        assert s["capability_governor_enabled"] is False
        assert s["adaptive_fingerprint_enabled"] is False
        assert s["causality_enabled"] is False

    def test_stats_when_all_on(self):
        k = _kernel_all_on()
        s = k.v2_stats()
        assert s["circuit_breaker_enabled"] is True
        assert s["capability_governor_enabled"] is True
        assert s["adaptive_fingerprint_enabled"] is True
        assert s["causality_enabled"] is True

    def test_stats_has_bus_depth(self):
        k = _kernel_all_off()
        s = k.v2_stats()
        assert "event_bus_queue_depth" in s


# ===========================================================================
# v1 backward compatibility
# ===========================================================================

class TestV1BackwardCompat:
    def test_v1_flow_unchanged(self):
        """Audit log entry still recorded when only v1 flags active."""
        cfg = SecurityConfig(forensic_audit=True, fingerprint_enabled=False)
        k = SecurityKernelV2(_registry(), cfg)
        env = _env()
        k.before_route(env)
        k.after_route(env, _ok_response())
        entries = k.audit_log.export()
        assert len(entries) >= 1

    def test_on_error_in_v1_mode(self):
        cfg = SecurityConfig(forensic_audit=True, fingerprint_enabled=False)
        k = SecurityKernelV2(_registry(), cfg)
        env = _env()
        k.before_route(env)
        k.on_error(env, ErrorInfo(code=ErrorCode.AGENT_ERROR, message="x",
                                   retryable=False, details={}))
        entries = k.audit_log.export()
        assert any(e["decision"] == "error" for e in entries)

    def test_idempotency_stats_still_works(self):
        cfg = SecurityConfig(idempotency_enabled=True, fingerprint_enabled=False)
        k = SecurityKernelV2(_registry(), cfg)
        stats = k.idempotency_stats()
        assert "total_keys" in stats

    def test_fingerprint_engine_accessible(self):
        k = _kernel_all_off()
        assert k.fingerprint_engine is not None


# ===========================================================================
# adaptive fingerprint wiring
# ===========================================================================

class TestAdaptiveFingerprint:
    def test_fp2_records_after_route(self):
        fp2 = AdaptiveFingerprintEngineV2()
        k = SecurityKernelV2(_registry(), fingerprint_v2=fp2)
        env = _env(intent="fp.test", request_id="fp-exec-1")
        k.before_route(env)
        k.after_route(env, _ok_response())
        # After recording, the intent should be known to fp2
        assert "fp.test" in fp2.known_intents()


# ===========================================================================
# Thread safety
# ===========================================================================

class TestThreadSafety:
    def test_parallel_before_after_route(self):
        """Multiple threads can drive the kernel concurrently."""
        k = _kernel_all_on()
        errors = []

        def cycle(i: int) -> None:
            try:
                env = _env(intent="test.intent", request_id=f"req-{i}")
                k.before_route(env)
                k.after_route(env, _ok_response())
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=cycle, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors

    def test_parallel_check_allowed(self):
        k = _kernel_all_on()
        results = []
        lock = threading.Lock()

        def worker():
            ok, _ = k.check_allowed("test.intent")
            with lock:
                results.append(ok)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(results) == 10
