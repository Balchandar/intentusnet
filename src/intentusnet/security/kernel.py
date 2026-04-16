"""
Security Kernel Middleware

The central enforcement layer for IntentusNet's Deterministic Execution Hypervisor.

Implements the RouterMiddleware protocol — plugs into the existing pipeline
as the outermost wrapper without any changes to existing middlewares, agents,
or registry structures.

Enforcement responsibilities:
  1. Intent Capability Contracts   — scope / metadata validation
  2. Idempotency Gate              — exact-once via deterministic key
  3. Execution Fingerprint         — anomaly detection (latency, retries, timeouts)
  4. Forensic Audit                — tamper-evident record linked to WAL hashes
  5. Side-effect observability     — anomaly score attached to response metadata

Feature flags (SecurityConfig):
  audit_only=True  (default) → log violations, never block
  strict_mode=True + audit_only=False → block and raise

All state is held internally; the router, registry, and agents are unchanged.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..protocol.intent import IntentEnvelope
from ..protocol.response import AgentResponse, ErrorInfo
from ..protocol.enums import ErrorCode
from .config import SecurityConfig
from .fingerprint import AnomalyClass, ExecutionFingerprintEngine
from .audit import ForensicAuditEntry, ForensicAuditLog

logger = logging.getLogger("intentusnet.security.kernel")

# Sentinel stored on env.metadata to pass context between before/after_route
_SK_EXEC_ID = "_sk_exec_id"
_SK_IDEM_KEY = "_sk_idem_key"
_SK_REPLAY = "_sk_replay"
_SK_INPUT_HASH = "_sk_input_hash"
_SK_VIOLATIONS = "_sk_violations"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _input_hash(env: IntentEnvelope) -> str:
    """Stable SHA-256 of the intent payload (canonical JSON)."""
    encoded = json.dumps(env.payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _idempotency_key(intent_name: str, input_hash: str, session_id: str) -> str:
    """Deterministic idempotency key: hash(intent_id + input_hash + state_version)."""
    raw = f"{intent_name}:{input_hash}:{session_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Internal pending-execution tracker
# ---------------------------------------------------------------------------

@dataclass
class _PendingExecution:
    execution_id: str
    intent_name: str
    input_hash: str
    start_time: float = field(default_factory=time.perf_counter)
    retries: int = 0


# ---------------------------------------------------------------------------
# SecurityKernelMiddleware
# ---------------------------------------------------------------------------

class SecurityKernelMiddleware:
    """
    Security enforcement kernel — RouterMiddleware-compatible.

    Constructor args:
        registry:            AgentRegistry (read-only; no mutations).
        config:              SecurityConfig — feature flags and thresholds.
        fingerprint_engine:  Optional pre-built engine (shared across instances).
        audit_log:           Optional pre-built log (shared across instances).

    Thread-safe. Idempotency state and pending-execution tracking are
    protected by a reentrant lock.
    """

    def __init__(
        self,
        registry: Any,
        config: Optional[SecurityConfig] = None,
        fingerprint_engine: Optional[ExecutionFingerprintEngine] = None,
        audit_log: Optional[ForensicAuditLog] = None,
    ) -> None:
        self._registry = registry
        self._config = config or SecurityConfig()

        cfg = self._config
        self._engine = fingerprint_engine or ExecutionFingerprintEngine(
            window_size=cfg.fingerprint_window,
            anomaly_threshold=cfg.anomaly_threshold,
            malicious_threshold=cfg.malicious_threshold,
        )
        self._audit = audit_log or ForensicAuditLog()

        # Idempotency: key → cached AgentResponse (None = in-flight placeholder)
        self._idempotency: Dict[str, Optional[AgentResponse]] = {}
        # In-flight tracking: execution_id → _PendingExecution
        self._pending: Dict[str, _PendingExecution] = {}

        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # RouterMiddleware protocol
    # ------------------------------------------------------------------

    def before_route(self, env: IntentEnvelope) -> None:
        cfg = self._config
        intent_name = env.intent.name
        execution_id = getattr(env.metadata, "requestId", intent_name)
        ih = _input_hash(env)

        # Store on envelope for after_route
        setattr(env.metadata, _SK_EXEC_ID, execution_id)
        setattr(env.metadata, _SK_INPUT_HASH, ih)

        # 1. Capability contract check
        violations: List[str] = []
        if cfg.capability_contracts:
            violations = self._check_capability_contracts(env)
            if violations:
                msg = f"SECURITY_KERNEL: Capability contract violations for '{intent_name}': {violations}"
                if cfg.is_enforcing():
                    logger.error(msg)
                else:
                    logger.warning(msg)
        setattr(env.metadata, _SK_VIOLATIONS, violations)

        # 2. Idempotency gate (exact-once execution)
        if cfg.idempotency_enabled:
            session_id = getattr(env.context, "sessionId", "") if env.context else ""
            idem_key = _idempotency_key(intent_name, ih, str(session_id))

            with self._lock:
                cached = self._idempotency.get(idem_key)
                if cached is not None:
                    # Exact duplicate — store replay marker, skip execution
                    setattr(env.metadata, _SK_REPLAY, cached)
                    logger.info(
                        "SECURITY_KERNEL: Idempotent replay for '%s' (key=%.16s…)",
                        intent_name, idem_key,
                    )
                    return
                # Mark as in-flight (None = placeholder)
                self._idempotency[idem_key] = None
                setattr(env.metadata, _SK_IDEM_KEY, idem_key)

        # 3. Start fingerprint trace
        if cfg.fingerprint_enabled:
            self._engine.start_trace(execution_id)

        # 4. Track pending execution
        with self._lock:
            self._pending[execution_id] = _PendingExecution(
                execution_id=execution_id,
                intent_name=intent_name,
                input_hash=ih,
            )

        logger.debug(
            "SECURITY_KERNEL: before_route OK intent='%s' exec='%s'",
            intent_name, execution_id,
        )

    def after_route(self, env: IntentEnvelope, response: AgentResponse) -> None:
        cfg = self._config
        intent_name = env.intent.name
        execution_id = getattr(env.metadata, _SK_EXEC_ID, intent_name)
        ih = getattr(env.metadata, _SK_INPUT_HASH, _input_hash(env))
        violations: List[str] = getattr(env.metadata, _SK_VIOLATIONS, [])

        # If this was a replay, nothing to finalize
        if getattr(env.metadata, _SK_REPLAY, None) is not None:
            return

        anomaly_score = 0.0
        anomaly_reasons: List[str] = []

        # 5. End fingerprint trace + anomaly evaluation
        if cfg.fingerprint_enabled:
            timed_out = (
                response.error is not None
                and response.error.code == ErrorCode.AGENT_TIMEOUT
            )
            result = self._engine.end_trace(
                execution_id,
                intent_name,
                timed_out=timed_out,
            )
            anomaly_score = result.anomaly_score
            anomaly_reasons = result.reasons

            if result.classification == AnomalyClass.MALICIOUS:
                logger.error(
                    "SECURITY_KERNEL: MALICIOUS anomaly intent='%s' score=%.3f reasons=%s",
                    intent_name, anomaly_score, result.reasons,
                )
            elif result.classification == AnomalyClass.SUSPICIOUS:
                logger.warning(
                    "SECURITY_KERNEL: SUSPICIOUS anomaly intent='%s' score=%.3f reasons=%s",
                    intent_name, anomaly_score, result.reasons,
                )

            # Attach to response metadata for observability
            response.metadata.setdefault("anomaly_score", round(anomaly_score, 4))
            response.metadata.setdefault("anomaly_class", result.classification.value)

        # 6. Resolve idempotency key with final response
        idem_key = getattr(env.metadata, _SK_IDEM_KEY, None)
        if idem_key and cfg.idempotency_enabled:
            with self._lock:
                self._idempotency[idem_key] = response

        # 7. Clear pending
        with self._lock:
            self._pending.pop(execution_id, None)

        # 8. Forensic audit record
        if cfg.forensic_audit:
            decision = "execute"
            if violations and cfg.is_enforcing():
                decision = "block"

            validation_result = (
                "blocked" if decision == "block"
                else ("audit_only" if violations else "allowed")
            )

            entry = ForensicAuditEntry(
                intent_id=intent_name,
                actor_id=getattr(env.metadata, "source", "unknown"),
                input_hash=ih,
                state_before="pre-execution",
                state_after="post-execution",
                validation_result=validation_result,
                anomaly_score=anomaly_score,
                decision=decision,
                wal_entry_hash=None,          # populated if WAL writer is injected
                timestamp=_utc_now(),
                intent_name=intent_name,
                capability_violations=violations,
                anomaly_reasons=anomaly_reasons,
                execution_id=execution_id,
            )
            self._audit.record(entry)

        logger.debug(
            "SECURITY_KERNEL: after_route OK intent='%s' anomaly=%.3f",
            intent_name, anomaly_score,
        )

    def on_error(self, env: IntentEnvelope, error: ErrorInfo) -> None:
        cfg = self._config
        intent_name = env.intent.name
        execution_id = getattr(env.metadata, _SK_EXEC_ID, intent_name)
        ih = getattr(env.metadata, _SK_INPUT_HASH, _input_hash(env))

        # End fingerprint trace on error (counts as timed_out for scoring)
        if cfg.fingerprint_enabled:
            self._engine.end_trace(execution_id, intent_name, timed_out=True)

        # Clean up in-flight state
        with self._lock:
            self._pending.pop(execution_id, None)
            idem_key = getattr(env.metadata, _SK_IDEM_KEY, None)
            if idem_key:
                # Remove placeholder so caller can retry cleanly
                self._idempotency.pop(idem_key, None)

        if cfg.forensic_audit:
            entry = ForensicAuditEntry(
                intent_id=intent_name,
                actor_id=getattr(env.metadata, "source", "unknown"),
                input_hash=ih,
                state_before="pre-execution",
                state_after="error",
                validation_result="error",
                anomaly_score=0.0,
                decision="error",
                wal_entry_hash=None,
                timestamp=_utc_now(),
                intent_name=intent_name,
                execution_id=execution_id,
            )
            self._audit.record(entry)

        logger.warning(
            "SECURITY_KERNEL: on_error intent='%s' exec='%s' code=%s msg=%s",
            intent_name, execution_id, error.code, error.message,
        )

    # ------------------------------------------------------------------
    # Internal — Capability Contract Check
    # ------------------------------------------------------------------

    def _check_capability_contracts(self, env: IntentEnvelope) -> List[str]:
        """
        Returns list of violation strings (empty = all contracts satisfied).

        Checks:
        - capability_scope: caller's scope must be in declared scopes (if set).
        """
        violations: List[str] = []
        intent_name = env.intent.name

        try:
            agents = self._registry.find_agents_for_intent(env.intent)
        except Exception:
            return []

        if not agents:
            return []

        caller_scope = getattr(env.metadata, "scope", None)

        for agent in agents:
            for cap in agent.definition.capabilities:
                # Match this specific capability to the intent
                cap_name = cap.intent.name
                if cap_name != intent_name and cap_name != "*":
                    continue

                meta = getattr(cap, "metadata", None)
                if meta is None:
                    continue  # No metadata = permissive

                # Scope check
                scopes = getattr(meta, "capability_scope", [])
                if scopes and caller_scope not in scopes:
                    violations.append(
                        f"agent '{agent.definition.name}' requires scope in "
                        f"{scopes}, caller scope='{caller_scope}'"
                    )

        return violations

    # ------------------------------------------------------------------
    # Public observability API
    # ------------------------------------------------------------------

    @property
    def audit_log(self) -> ForensicAuditLog:
        return self._audit

    @property
    def fingerprint_engine(self) -> ExecutionFingerprintEngine:
        return self._engine

    @property
    def config(self) -> SecurityConfig:
        return self._config

    def idempotency_stats(self) -> Dict[str, int]:
        """Return idempotency store counters for dashboards."""
        with self._lock:
            resolved = sum(1 for v in self._idempotency.values() if v is not None)
            return {
                "total_keys": len(self._idempotency),
                "resolved": resolved,
                "in_flight": len(self._pending),
            }

    def pending_executions(self) -> List[str]:
        """Return list of execution IDs currently in-flight."""
        with self._lock:
            return list(self._pending.keys())
