"""
Security Kernel v2.1 — Adaptive Fingerprint Engine

Production-grade replacement for ExecutionFingerprintEngine (v1).

Key improvements over v1
------------------------
1. Dual-baseline EWMA (short α=0.10, long α=0.01) replaces the fixed sliding
   window.  The short baseline detects spikes; the long baseline detects drift.
2. Baseline freeze: when ``drift_score ≥ 0.50`` the baselines stop updating so
   that a sustained attack cannot poison the learned normal profile.
3. Decomposed signals: latency and behaviour are scored independently via the
   ``signals.compute()`` pipeline, preventing correlated false positives.
4. Optional SecurityEventBus integration: anomalies are emitted as
   ``ANOMALY_DETECTED`` events for downstream consumers (circuit breaker, audit).

Backward compatibility
----------------------
``AdaptiveFingerprintEngineV2`` provides the same ``start_trace`` / ``end_trace``
interface as the v1 engine so it can be used as a drop-in replacement in
``SecurityKernelMiddleware``.  The ``record()`` method is an ergonomic alternative
that accepts an explicit latency value (useful in tests and replay scenarios).

Signal routing
--------------
The fingerprint engine consumes ``latency_signal`` and ``behavior_signal`` only.
``error_signal`` goes to the CircuitBreaker; ``policy_signal`` goes to the
ForensicAuditLog.  Keeping concerns separated prevents a single mis-classified
event from triggering every defence simultaneously.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .event_bus import SecurityEvent, SecurityEventBus, SecurityEventType
from .fingerprint import AnomalyClass, AnomalyResult
from .signals import (
    DecomposedSignalSet,
    DualBaselineResult,
    _BaselineRegistry,
    compute,
)


# ---------------------------------------------------------------------------
# Observability snapshot
# ---------------------------------------------------------------------------

@dataclass
class EWMAProfile:
    """
    Current EWMA state for one intent's latency dimension.

    Returned by ``AdaptiveFingerprintEngineV2.get_profile()``.
    All latency values are in milliseconds.
    """
    intent_name:           str
    latency_short_ema:     float
    latency_long_ema:      float
    latency_drift_score:   float
    latency_baseline_frozen: bool

    def to_dict(self) -> Dict:
        return {
            "intent":                  self.intent_name,
            "latency_short_ema_ms":    round(self.latency_short_ema, 2),
            "latency_long_ema_ms":     round(self.latency_long_ema, 2),
            "latency_drift_score":     round(self.latency_drift_score, 4),
            "latency_baseline_frozen": self.latency_baseline_frozen,
        }


# ---------------------------------------------------------------------------
# Adaptive Fingerprint Engine v2
# ---------------------------------------------------------------------------

class AdaptiveFingerprintEngineV2:
    """
    Adaptive, dual-baseline behavioural anomaly detector.

    Thread-safe.  Each instance maintains its own ``_BaselineRegistry`` so
    different intents are fully isolated and the module-level registry used
    by ``signals.compute()`` is not polluted.

    Parameters
    ----------
    anomaly_threshold
        ``anomaly_score >= this`` → SUSPICIOUS.
    malicious_threshold
        ``anomaly_score >= this`` → MALICIOUS.
    latency_weight
        Multiplier applied to the latency signal before final scoring.
        Reducing this de-emphasises latency relative to behaviour.
    behavior_weight
        Multiplier applied to the behaviour signal.
    event_bus
        If set, ``ANOMALY_DETECTED`` events are emitted for SUSPICIOUS and
        MALICIOUS results.
    latency_anomaly_threshold_ms
        Absolute latency at which the sigmoid midpoint sits (fallback when
        EWMA variance is zero).
    error_threshold
        Consecutive errors at which ``error_signal`` reaches 0.5.
    behavior_threshold
        Combined unexpected-capabilities + policy-violations count at which
        ``behavior_signal`` reaches 0.5.
    """

    # Signals below this level are not included in the reasons list.
    _REASON_SIGNAL_THRESHOLD = 0.35

    def __init__(
        self,
        anomaly_threshold:            float = 0.75,
        malicious_threshold:          float = 0.95,
        latency_weight:               float = 1.0,
        behavior_weight:              float = 0.9,
        event_bus:                    Optional[SecurityEventBus] = None,
        latency_anomaly_threshold_ms: float = 500.0,
        error_threshold:              int   = 3,
        behavior_threshold:           int   = 1,
    ) -> None:
        self._anomaly_threshold            = anomaly_threshold
        self._malicious_threshold          = malicious_threshold
        self._latency_weight               = latency_weight
        self._behavior_weight              = behavior_weight
        self._event_bus                    = event_bus
        self._latency_anomaly_threshold_ms = latency_anomaly_threshold_ms
        self._error_threshold              = error_threshold
        self._behavior_threshold           = behavior_threshold

        self._registry                     = _BaselineRegistry()
        self._active_starts: Dict[str, float] = {}
        self._known_intents: set            = set()
        self._lock                         = threading.Lock()

    # ------------------------------------------------------------------
    # v1-compatible trace lifecycle
    # ------------------------------------------------------------------

    def start_trace(self, execution_id: str) -> None:
        """Record the wall-clock start of an execution trace."""
        with self._lock:
            self._active_starts[execution_id] = time.perf_counter()

    def end_trace(
        self,
        execution_id: str,
        intent_name:  str,
        *,
        retries:                  int   = 0,
        timed_out:                bool  = False,
        unexpected_capabilities:  int   = 0,
        policy_violations:        int   = 0,
        policy_score:             float = 0.0,
    ) -> AnomalyResult:
        """
        Record end of execution; evaluate against EWMA baselines.

        Parameters mirror the v1 ``ExecutionFingerprintEngine.end_trace()``
        signature so this class can be used as a drop-in replacement.

        The ``retries`` parameter maps to ``consecutive_errors`` in the signal
        layer (high retry counts correlate with error conditions).
        """
        with self._lock:
            start = self._active_starts.pop(execution_id, None)
            latency_ms = (
                (time.perf_counter() - start) * 1000.0
                if start is not None
                else 0.0
            )

        return self.record(
            intent_name,
            execution_id,
            latency_ms=latency_ms,
            error_occurred=timed_out,
            consecutive_errors=retries,
            timed_out=timed_out,
            unexpected_capabilities=unexpected_capabilities,
            policy_violations=policy_violations,
            policy_score=policy_score,
        )

    # ------------------------------------------------------------------
    # Direct recording (ergonomic API)
    # ------------------------------------------------------------------

    def record(
        self,
        intent_name:             str,
        execution_id:            str,
        *,
        latency_ms:              float,
        error_occurred:          bool  = False,
        consecutive_errors:      int   = 0,
        timed_out:               bool  = False,
        unexpected_capabilities: int   = 0,
        policy_violations:       int   = 0,
        policy_score:            float = 0.0,
    ) -> AnomalyResult:
        """
        Compute signals for one observation and return an AnomalyResult.

        Unlike ``end_trace()``, the caller supplies ``latency_ms`` directly —
        useful in tests and in the deterministic replay engine where real timing
        is not meaningful.
        """
        with self._lock:
            self._known_intents.add(intent_name)

        signals = compute(
            intent_name,
            latency_ms=latency_ms,
            latency_anomaly_threshold_ms=self._latency_anomaly_threshold_ms,
            error_occurred=error_occurred or timed_out,
            consecutive_errors=consecutive_errors,
            error_threshold=self._error_threshold,
            unexpected_capabilities=unexpected_capabilities,
            policy_violations=policy_violations,
            behavior_threshold=self._behavior_threshold,
            policy_score=policy_score,
            registry=self._registry,
        )

        result = self._score(signals, intent_name, latency_ms)

        if result.classification != AnomalyClass.NORMAL and self._event_bus is not None:
            self._event_bus.emit(
                SecurityEventType.ANOMALY_DETECTED,
                intent_name,
                execution_id=execution_id,
                payload={
                    "anomaly_score":    result.anomaly_score,
                    "classification":   result.classification.value,
                    "reasons":          result.reasons,
                    "signals":          signals.to_dict(),
                    "latency_ms":       latency_ms,
                },
            )

        return result

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score(
        self,
        signals:     DecomposedSignalSet,
        intent_name: str,
        latency_ms:  float,
    ) -> AnomalyResult:
        """
        Convert a DecomposedSignalSet into an AnomalyResult.

        The fingerprint engine uses ONLY latency_signal and behavior_signal.
        Routing error/policy signals to other subsystems prevents a single
        anomalous execution from triggering every defence at once.
        """
        reasons: List[str] = []

        lat = signals.latency_signal * self._latency_weight
        beh = signals.behavior_signal * self._behavior_weight

        if signals.latency_signal >= self._REASON_SIGNAL_THRESHOLD:
            bl: Optional[DualBaselineResult] = signals.latency_baseline
            z_part     = (f" z={bl.z_score:.2f}" if bl and bl.z_score is not None else "")
            drift_part = (f" drift={bl.drift_score:.3f}" if bl else "")
            frozen_tag = (" [frozen]" if bl and bl.baseline_frozen else "")
            ema_part   = (
                f" ema_short={bl.short_ema:.1f}ms ema_long={bl.long_ema:.1f}ms"
                if bl else ""
            )
            reasons.append(
                f"latency_anomaly signal={signals.latency_signal:.3f}"
                f"{z_part}{drift_part}{frozen_tag}"
                f" sample={latency_ms:.1f}ms{ema_part}"
            )

        if signals.behavior_signal >= self._REASON_SIGNAL_THRESHOLD:
            reasons.append(
                f"behavior_anomaly signal={signals.behavior_signal:.3f}"
            )

        score = min(1.0, max(lat, beh))

        if score >= self._malicious_threshold:
            cls = AnomalyClass.MALICIOUS
        elif score >= self._anomaly_threshold:
            cls = AnomalyClass.SUSPICIOUS
        else:
            cls = AnomalyClass.NORMAL

        return AnomalyResult(score, cls, reasons)

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def get_profile(self, intent_name: str) -> Optional[EWMAProfile]:
        """
        Return the current EWMA baseline state for an intent.

        Returns ``None`` if no observations have been recorded for this intent.
        """
        bl = self._registry.peek(intent_name, "latency")
        if bl is None:
            return None
        return EWMAProfile(
            intent_name=intent_name,
            latency_short_ema=round(bl.short_ema, 2),
            latency_long_ema=round(bl.long_ema, 2),
            latency_drift_score=round(bl.drift_score, 4),
            latency_baseline_frozen=bl.baseline_frozen,
        )

    def known_intents(self) -> List[str]:
        """Return the list of intent names seen so far."""
        with self._lock:
            return sorted(self._known_intents)

    def reset_intent(self, intent_name: str) -> None:
        """Clear the EWMA baseline for an intent (e.g. after a deployment)."""
        self._registry.reset_intent(intent_name)
        with self._lock:
            self._known_intents.discard(intent_name)
