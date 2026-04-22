"""
Security Kernel v2.1 — Unified Enforcement Middleware

Extends ``SecurityKernelMiddleware`` (v1) by wiring every v2.1 subsystem into
the RouterMiddleware lifecycle.  All v2 features default to OFF so upgrading
from v1 requires no configuration changes.

v2.1 enforcement model
-----------------------
``before_route``
  1. Backpressure gate — FAIL_SAFE state blocks new requests when enforcing.
  2. Circuit breaker — OPEN state blocks an intent when enforcing.
  3. Capability governor — suspended intent/capability blocks when enforcing.
  4. (Future) policy engine v2 pre-check hook.
  5. Emit ``EXECUTION_STARTED`` to SecurityEventBus.
  6. Causality registration (if enabled).

``after_route``
  Calls v1 super(), then:
  7. Compute signals via AdaptiveFingerprintEngineV2 (latency + behaviour).
  8. Record outcome to CircuitBreaker (drives OPEN/HALF_OPEN transitions).
  9. Record behaviour signal to CapabilityGovernor.
  10. Update BackpressureManager with current event-bus queue depth.
  11. Emit ``EXECUTION_COMPLETED`` / ``DEGRADATION_STATE_CHANGED`` events.

``on_error``
  Calls v1 super(), then:
  12. Record failure to CircuitBreaker (error_occurred=True).
  13. Update BackpressureManager.
  14. Emit ``EXECUTION_FAILED``.

Enforcement levels
------------------
* ``audit_only=True`` (default): all v2 checks observe and emit events but
  NEVER block. The request proceeds regardless.
* ``strict_mode=True, audit_only=False``: v2 checks can mark a request as
  blocked.  Blocked status is stored on ``env.metadata._sk_v2_blocked`` so
  a hardened router or gateway can reject the response before returning it
  to the caller.  The ``check_allowed()`` method provides a synchronous
  permit check suitable for use in custom entry points.

Thread safety
-------------
All v2 state objects are individually thread-safe.  ``before_route`` and
``after_route`` share no mutable state beyond what is protected inside each
subsystem's own lock.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from ..protocol.intent import IntentEnvelope
from ..protocol.response import AgentResponse, ErrorInfo
from ..protocol.enums import ErrorCode
from .backpressure import BackpressureManager, BackpressureMetrics, from_config as bp_from_config
from .capability_governor_v2 import CapabilityGovernor
from .causality_index import CausalityIndex, ExecutionNode
from .circuit_breaker_v2 import CircuitBreaker
from .config import SecurityConfig
from .event_bus import SecurityEventBus, SecurityEventType
from .fingerprint_v2 import AdaptiveFingerprintEngineV2
from .kernel import SecurityKernelMiddleware, _SK_EXEC_ID, _SK_INPUT_HASH
from .signals import DecomposedSignalSet, compute as compute_signals
from .types import DegradationState

logger = logging.getLogger("intentusnet.security.kernel_v2")

# Extra env.metadata sentinels used only by v2
_SK_V2_BLOCKED      = "_sk_v2_blocked"       # str: reason why blocked (or None)
_SK_V2_START_PERF   = "_sk_v2_start_perf"    # float: perf_counter at before_route


class SecurityKernelV2(SecurityKernelMiddleware):
    """
    RouterMiddleware-compatible security kernel with full v2.1 wiring.

    All v2 components are optional and disabled unless the corresponding
    SecurityConfig flag is True.

    Parameters
    ----------
    registry
        AgentRegistry (passed to v1 super).
    config
        SecurityConfig with v2.1 flags.  Defaults to a fully-passive config.
    event_bus
        Pre-built SecurityEventBus.  Created automatically when
        ``config.security_trace_enabled=True`` and none is supplied.
    circuit_breaker
        Pre-built CircuitBreaker.  Created automatically when
        ``config.circuit_breaker_enabled=True`` and none is supplied.
    capability_governor
        Pre-built CapabilityGovernor.  Created automatically when
        ``config.capability_governor_enabled=True`` and none is supplied.
    backpressure_manager
        Pre-built BackpressureManager.  Created automatically when
        ``config.backpressure_enabled=True`` and none is supplied.
    fingerprint_v2
        Pre-built AdaptiveFingerprintEngineV2.  Created automatically when
        ``config.adaptive_fingerprint=True`` and none is supplied.
    causality_index
        Pre-built CausalityIndex.  Created automatically when
        ``config.causality_tracking_enabled=True`` and none is supplied.
    """

    def __init__(
        self,
        registry:            Any,
        config:              Optional[SecurityConfig] = None,
        *,
        event_bus:           Optional[SecurityEventBus] = None,
        circuit_breaker:     Optional[CircuitBreaker] = None,
        capability_governor: Optional[CapabilityGovernor] = None,
        backpressure_manager: Optional[BackpressureManager] = None,
        fingerprint_v2:      Optional[AdaptiveFingerprintEngineV2] = None,
        causality_index:     Optional[CausalityIndex] = None,
        **kwargs: Any,
    ) -> None:
        cfg = config or SecurityConfig()
        super().__init__(registry, cfg, **kwargs)

        # Event bus
        if event_bus is not None:
            self._event_bus_v2: Optional[SecurityEventBus] = event_bus
        elif cfg.security_trace_enabled:
            self._event_bus_v2 = SecurityEventBus(
                max_queue=cfg.event_bus_max_queue,
            )
        else:
            self._event_bus_v2 = None

        # Circuit breaker
        if circuit_breaker is not None:
            self._cb: Optional[CircuitBreaker] = circuit_breaker
        elif cfg.circuit_breaker_enabled:
            self._cb = CircuitBreaker(
                failure_threshold=cfg.circuit_breaker_failure_threshold,
                timeout_seconds=cfg.circuit_breaker_timeout_seconds,
                event_bus=self._event_bus_v2,
            )
        else:
            self._cb = None

        # Capability governor
        if capability_governor is not None:
            self._gov: Optional[CapabilityGovernor] = capability_governor
        elif cfg.capability_governor_enabled:
            self._gov = CapabilityGovernor(
                behavior_threshold=cfg.capability_governor_threshold,
                event_bus=self._event_bus_v2,
            )
        else:
            self._gov = None

        # Backpressure
        if backpressure_manager is not None:
            self._bp: Optional[BackpressureManager] = backpressure_manager
        elif cfg.backpressure_enabled:
            self._bp = bp_from_config(cfg)
        else:
            self._bp = None

        # Adaptive fingerprint v2
        if fingerprint_v2 is not None:
            self._fp2: Optional[AdaptiveFingerprintEngineV2] = fingerprint_v2
        elif cfg.adaptive_fingerprint:
            self._fp2 = AdaptiveFingerprintEngineV2(
                anomaly_threshold=cfg.anomaly_threshold,
                malicious_threshold=cfg.malicious_threshold,
                event_bus=self._event_bus_v2,
            )
        else:
            self._fp2 = None

        # Causality index
        if causality_index is not None:
            self._causality: Optional[CausalityIndex] = causality_index
        elif cfg.causality_tracking_enabled:
            self._causality = CausalityIndex(
                segment_size=cfg.causality_segment_size,
            )
        else:
            self._causality = None

    # ------------------------------------------------------------------
    # RouterMiddleware — before_route
    # ------------------------------------------------------------------

    def before_route(self, env: IntentEnvelope) -> None:
        """Run v1 checks then v2 gate checks."""
        # Record perf timer BEFORE super (so latency includes v1 overhead)
        setattr(env.metadata, _SK_V2_START_PERF, time.perf_counter())

        # v1 checks (idempotency, capability contracts, fingerprint start)
        super().before_route(env)

        cfg    = self._config
        intent = env.intent.name

        # ------------------------------------------------------------------
        # Backpressure gate
        # ------------------------------------------------------------------
        if self._bp is not None:
            state = self._bp.current_state
            if state == DegradationState.FAIL_SAFE:
                reason = f"backpressure FAIL_SAFE: all new requests rejected"
                self._record_v2_block(env, reason)
                logger.error(
                    "SECURITY_KERNEL_V2: FAIL_SAFE blocks intent='%s'", intent,
                )
                if self._event_bus_v2:
                    self._event_bus_v2.emit(
                        SecurityEventType.EXECUTION_FAILED,
                        intent,
                        payload={"reason": reason, "degradation_state": state.value},
                    )
                return

        # ------------------------------------------------------------------
        # Circuit breaker gate
        # ------------------------------------------------------------------
        if self._cb is not None:
            if not self._cb.allow(intent):
                reason = f"circuit breaker OPEN for intent='{intent}'"
                self._record_v2_block(env, reason)
                logger.warning(
                    "SECURITY_KERNEL_V2: circuit OPEN for intent='%s'", intent,
                )
                if self._event_bus_v2:
                    self._event_bus_v2.emit(
                        SecurityEventType.EXECUTION_FAILED,
                        intent,
                        payload={"reason": reason, "circuit_state": "open"},
                    )
                return

        # ------------------------------------------------------------------
        # Capability governor gate
        # ------------------------------------------------------------------
        if self._gov is not None:
            if not self._gov.is_allowed(intent):
                reason = f"capability governor: intent='{intent}' suspended"
                self._record_v2_block(env, reason)
                logger.warning(
                    "SECURITY_KERNEL_V2: intent='%s' suspended by CapabilityGovernor",
                    intent,
                )
                if self._event_bus_v2:
                    self._event_bus_v2.emit(
                        SecurityEventType.CAPABILITY_VIOLATION,
                        intent,
                        payload={"reason": reason, "whole_intent": True},
                    )
                return

        # ------------------------------------------------------------------
        # Causality registration
        # ------------------------------------------------------------------
        if self._causality is not None:
            execution_id = getattr(env.metadata, _SK_EXEC_ID, intent)
            parent_id = getattr(env.metadata, "parentExecutionId", None)
            depth = 0 if parent_id is None else 1
            node = ExecutionNode(
                execution_id=execution_id,
                agent_id=intent,
                step_seq=0,
                depth=depth,
                parent_id=parent_id,
                metadata={"intent_name": intent},
            )
            self._causality.add_node(node)

        # ------------------------------------------------------------------
        # Emit EXECUTION_STARTED
        # ------------------------------------------------------------------
        if self._event_bus_v2:
            execution_id = getattr(env.metadata, _SK_EXEC_ID, intent)
            self._event_bus_v2.emit(
                SecurityEventType.EXECUTION_STARTED,
                intent,
                execution_id=execution_id,
                payload={"intent": intent},
            )

    # ------------------------------------------------------------------
    # RouterMiddleware — after_route
    # ------------------------------------------------------------------

    def after_route(self, env: IntentEnvelope, response: AgentResponse) -> None:
        """Run v1 finalization then update all v2 subsystems."""
        super().after_route(env, response)

        intent       = env.intent.name
        execution_id = getattr(env.metadata, _SK_EXEC_ID, intent)
        start_perf   = getattr(env.metadata, _SK_V2_START_PERF, None)
        latency_ms   = (
            (time.perf_counter() - start_perf) * 1000.0
            if start_perf is not None
            else 0.0
        )
        timed_out    = (
            response.error is not None
            and response.error.code == ErrorCode.AGENT_TIMEOUT
        )
        success      = response.error is None

        # ------------------------------------------------------------------
        # Adaptive fingerprint v2 + signal computation
        # ------------------------------------------------------------------
        signals: Optional[DecomposedSignalSet] = None
        if self._fp2 is not None:
            anomaly = self._fp2.record(
                intent,
                execution_id,
                latency_ms=latency_ms,
                timed_out=timed_out,
                error_occurred=not success,
            )
            signals = compute_signals(
                intent,
                latency_ms=latency_ms,
                error_occurred=not success or timed_out,
                registry=self._fp2._registry,
            )
            logger.debug(
                "SECURITY_KERNEL_V2: fp2 intent='%s' score=%.3f cls=%s",
                intent, anomaly.anomaly_score, anomaly.classification.value,
            )

        # ------------------------------------------------------------------
        # Circuit breaker — record outcome
        # ------------------------------------------------------------------
        if self._cb is not None:
            self._cb.record(intent, signals, success=success)

        # ------------------------------------------------------------------
        # Capability governor — record behaviour signal
        # ------------------------------------------------------------------
        if self._gov is not None and signals is not None:
            self._gov.record(intent, signals.behavior_signal)

        # ------------------------------------------------------------------
        # Backpressure — update from current event-bus lag
        # ------------------------------------------------------------------
        if self._bp is not None:
            lag = self._event_bus_v2.queue_depth if self._event_bus_v2 else 0
            metrics = BackpressureMetrics(event_bus_lag=lag)
            transition = self._bp.update(metrics)
            if transition is not None:
                logger.warning(
                    "SECURITY_KERNEL_V2: backpressure %s→%s reason='%s'",
                    transition.from_state.value,
                    transition.to_state.value,
                    transition.reason,
                )
                if self._event_bus_v2:
                    self._event_bus_v2.emit(
                        SecurityEventType.DEGRADATION_STATE_CHANGED,
                        intent,
                        payload={
                            "from_state": transition.from_state.value,
                            "to_state":   transition.to_state.value,
                            "reason":     transition.reason,
                        },
                    )

        # ------------------------------------------------------------------
        # Emit EXECUTION_COMPLETED
        # ------------------------------------------------------------------
        if self._event_bus_v2:
            self._event_bus_v2.emit(
                SecurityEventType.EXECUTION_COMPLETED,
                intent,
                execution_id=execution_id,
                payload={
                    "latency_ms": round(latency_ms, 2),
                    "success":    success,
                },
            )

    # ------------------------------------------------------------------
    # RouterMiddleware — on_error
    # ------------------------------------------------------------------

    def on_error(self, env: IntentEnvelope, error: ErrorInfo) -> None:
        """Run v1 error handling then update v2 subsystems."""
        super().on_error(env, error)

        intent       = env.intent.name
        execution_id = getattr(env.metadata, _SK_EXEC_ID, intent)

        # Circuit breaker records failure
        if self._cb is not None:
            self._cb.record(intent, None, success=False)

        # Backpressure
        if self._bp is not None:
            lag = self._event_bus_v2.queue_depth if self._event_bus_v2 else 0
            self._bp.update(BackpressureMetrics(event_bus_lag=lag))

        # Emit EXECUTION_FAILED
        if self._event_bus_v2:
            self._event_bus_v2.emit(
                SecurityEventType.EXECUTION_FAILED,
                intent,
                execution_id=execution_id,
                payload={
                    "error_code":    error.code.value if hasattr(error.code, "value") else str(error.code),
                    "error_message": error.message,
                },
            )

    # ------------------------------------------------------------------
    # Synchronous permit check (for hardened gateways)
    # ------------------------------------------------------------------

    def check_allowed(self, intent_name: str) -> Tuple[bool, str]:
        """
        Synchronous permit check — does NOT mutate any state.

        Returns ``(True, "")`` when the intent may proceed, or
        ``(False, reason)`` when it should be rejected.

        Suitable for use in a custom entry point or gateway that needs a
        definitive permit/deny answer before executing the intent, without
        going through the RouterMiddleware lifecycle.
        """
        if self._bp is not None:
            if self._bp.current_state == DegradationState.FAIL_SAFE:
                return False, "backpressure FAIL_SAFE"

        if self._cb is not None:
            if not self._cb.allow(intent_name):
                return False, f"circuit OPEN for '{intent_name}'"

        if self._gov is not None:
            if not self._gov.is_allowed(intent_name):
                return False, f"capability governor: '{intent_name}' suspended"

        return True, ""

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    @property
    def event_bus(self) -> Optional[SecurityEventBus]:
        return self._event_bus_v2

    @property
    def circuit_breaker(self) -> Optional[CircuitBreaker]:
        return self._cb

    @property
    def capability_governor(self) -> Optional[CapabilityGovernor]:
        return self._gov

    @property
    def backpressure_manager(self) -> Optional[BackpressureManager]:
        return self._bp

    @property
    def adaptive_fingerprint(self) -> Optional[AdaptiveFingerprintEngineV2]:
        return self._fp2

    @property
    def causality(self) -> Optional[CausalityIndex]:
        return self._causality

    def v2_stats(self) -> Dict[str, Any]:
        """Return a snapshot of all v2 subsystem states."""
        cb_state  = self._cb.get_state if self._cb else None
        bp_state  = self._bp.current_state.value if self._bp else None
        bus_depth = self._event_bus_v2.queue_depth if self._event_bus_v2 else 0
        return {
            "backpressure_state": bp_state,
            "event_bus_queue_depth": bus_depth,
            "circuit_breaker_enabled": self._cb is not None,
            "capability_governor_enabled": self._gov is not None,
            "adaptive_fingerprint_enabled": self._fp2 is not None,
            "causality_enabled": self._causality is not None,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record_v2_block(self, env: IntentEnvelope, reason: str) -> None:
        """
        Mark the envelope as blocked by v2 enforcement.

        In audit_only mode the marker is set but enforcement is advisory;
        the caller (router / gateway) decides whether to honour it.
        """
        setattr(env.metadata, _SK_V2_BLOCKED, reason)
        if self._config.is_enforcing():
            logger.error(
                "SECURITY_KERNEL_V2: BLOCKING intent='%s' reason='%s'",
                env.intent.name, reason,
            )
        else:
            logger.warning(
                "SECURITY_KERNEL_V2: ADVISORY BLOCK (audit_only) intent='%s' reason='%s'",
                env.intent.name, reason,
            )
