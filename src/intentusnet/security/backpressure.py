"""
Security Kernel v2.1 — Backpressure / Degradation State Machine

Monitors runtime pressure metrics (event bus queue depth, WAL write backlog,
trust-anchor confirmation backlog) and transitions the system through four
degradation tiers when pressure rises.

Tiers (ordered worst-first)
---------------------------
  NORMAL            — full operation
  OBSERVATION_DROP  — non-critical security events dropped to shed load
  AUDIT_ONLY        — enforcement suspended; audit pipeline preserved
  FAIL_SAFE         — all new requests rejected

Transition rules
----------------
  Advance: immediately when any metric exceeds the threshold for the target tier.
  Recover: only after ALL metrics have been below the recovery threshold for the
           given state for at least ``hysteresis_seconds`` continuously.
  Recovery is one tier at a time (FAIL_SAFE → AUDIT_ONLY → … → NORMAL).

Enforcement
-----------
This module manages state only.  The actual enforcement actions (dropping
events, suspending circuits, rejecting requests) are wired in Phase 8.
State transitions are reported via an optional ``on_transition`` callback
and optionally emitted to the SecurityEventBus if one is provided.

Thread safety
-------------
All public methods acquire the instance lock.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from .types import DegradationState


# ---------------------------------------------------------------------------
# Metric snapshot
# ---------------------------------------------------------------------------

@dataclass
class BackpressureMetrics:
    """
    One snapshot of the pressure metrics fed to BackpressureManager.update().

    All counts are instantaneous samples (not rolling sums).
    """
    event_bus_lag:   int   = 0    # current depth of the security event bus queue
    wal_backlog:     int   = 0    # unconfirmed WAL entries pending fsync/chain
    anchor_backlog:  int   = 0    # trust-anchor confirmations outstanding
    observed_at:     float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Transition record
# ---------------------------------------------------------------------------

@dataclass
class BackpressureTransition:
    """Immutable record of a single state-machine transition."""
    from_state:  DegradationState
    to_state:    DegradationState
    reason:      str
    metrics:     BackpressureMetrics
    timestamp:   float = field(default_factory=time.time)

    @property
    def is_degradation(self) -> bool:
        return _STATE_RANK[self.to_state] > _STATE_RANK[self.from_state]

    @property
    def is_recovery(self) -> bool:
        return _STATE_RANK[self.to_state] < _STATE_RANK[self.from_state]


# ---------------------------------------------------------------------------
# State ordering helpers
# ---------------------------------------------------------------------------

_ORDERED_STATES = [
    DegradationState.NORMAL,
    DegradationState.OBSERVATION_DROP,
    DegradationState.AUDIT_ONLY,
    DegradationState.FAIL_SAFE,
]

_STATE_RANK: dict = {s: i for i, s in enumerate(_ORDERED_STATES)}

_ONE_BELOW = {
    DegradationState.FAIL_SAFE:         DegradationState.AUDIT_ONLY,
    DegradationState.AUDIT_ONLY:        DegradationState.OBSERVATION_DROP,
    DegradationState.OBSERVATION_DROP:  DegradationState.NORMAL,
    DegradationState.NORMAL:            DegradationState.NORMAL,
}


# ---------------------------------------------------------------------------
# BackpressureManager
# ---------------------------------------------------------------------------

class BackpressureManager:
    """
    Four-tier degradation state machine driven by pressure metrics.

    Parameters
    ----------
    observation_drop_thresholds
        (event_bus_lag, wal_backlog) that trigger OBSERVATION_DROP.
    audit_only_thresholds
        Same structure, for AUDIT_ONLY.
    fail_safe_thresholds
        Same structure, for FAIL_SAFE.
    hysteresis_seconds
        How long ALL metrics must stay below the recovery threshold before
        the state improves by one tier.
    initial_state
        Starting state (default NORMAL).
    on_transition
        Optional callback invoked synchronously on every state change.
        Signature: (transition: BackpressureTransition) -> None.
    max_history
        Maximum number of transitions retained in ``history``.
    """

    def __init__(
        self,
        *,
        observation_drop_thresholds: Tuple[int, int, int] = (5_000, 1_000, 0),
        audit_only_thresholds:       Tuple[int, int, int] = (8_000, 5_000, 0),
        fail_safe_thresholds:        Tuple[int, int, int] = (10_000, 9_000, 0),
        hysteresis_seconds:          float = 10.0,
        initial_state:               DegradationState = DegradationState.NORMAL,
        on_transition: Optional[Callable[[BackpressureTransition], None]] = None,
        max_history:   int = 1_000,
    ) -> None:
        # Threshold tuples: (event_bus_lag, wal_backlog, anchor_backlog)
        self._thresholds = {
            DegradationState.OBSERVATION_DROP: observation_drop_thresholds,
            DegradationState.AUDIT_ONLY:       audit_only_thresholds,
            DegradationState.FAIL_SAFE:        fail_safe_thresholds,
        }
        self._hysteresis_seconds = hysteresis_seconds
        self._on_transition      = on_transition
        self._max_history        = max_history

        self._state              = initial_state
        self._history:  List[BackpressureTransition] = []
        self._lock = threading.Lock()

        # Hysteresis: tracks when metrics first dropped below the recovery
        # threshold for the current state.  None = not yet in recovery window.
        self._recovery_started_at: Optional[float] = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_state(self) -> DegradationState:
        with self._lock:
            return self._state

    @property
    def history(self) -> List[BackpressureTransition]:
        with self._lock:
            return list(self._history)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, metrics: BackpressureMetrics) -> Optional[BackpressureTransition]:
        """
        Evaluate one metrics snapshot.

        Returns a ``BackpressureTransition`` if the state changed, else None.
        The ``on_transition`` callback is also invoked on change.
        """
        with self._lock:
            pressure_tier = self._compute_pressure_tier(metrics)
            current_rank  = _STATE_RANK[self._state]
            now           = metrics.observed_at

            # --- Degradation: advance immediately if pressure demands it ---
            if pressure_tier > current_rank:
                new_state = _ORDERED_STATES[pressure_tier]
                self._recovery_started_at = None
                return self._transition(new_state, metrics,
                                        reason=self._degradation_reason(new_state, metrics))

            # --- Recovery: one tier at a time with hysteresis ---
            if current_rank > 0:    # not already NORMAL
                recovery_state = _ORDERED_STATES[current_rank - 1]
                required_tier  = current_rank  # must be below current state's threshold

                if pressure_tier < required_tier:
                    if self._hysteresis_seconds <= 0:
                        # Zero hysteresis — recover one tier immediately
                        self._recovery_started_at = None
                        return self._transition(
                            recovery_state, metrics,
                            reason=f"recovered to {recovery_state.value} (no hysteresis)",
                        )
                    elif self._recovery_started_at is None:
                        self._recovery_started_at = now
                    elif (now - self._recovery_started_at) >= self._hysteresis_seconds:
                        self._recovery_started_at = None
                        return self._transition(
                            recovery_state, metrics,
                            reason=f"recovered to {recovery_state.value} after "
                                   f"{self._hysteresis_seconds}s below threshold",
                        )
                else:
                    # Pressure is back above threshold — reset recovery timer
                    self._recovery_started_at = None

            return None

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self, state: DegradationState = DegradationState.NORMAL) -> None:
        """Force-reset state (e.g. operator override).  Records a transition."""
        with self._lock:
            if self._state != state:
                metrics = BackpressureMetrics()
                self._transition(state, metrics, reason="operator reset")
            self._recovery_started_at = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_pressure_tier(self, m: BackpressureMetrics) -> int:
        """Return the highest tier (0–3) warranted by current metrics."""
        values = (m.event_bus_lag, m.wal_backlog, m.anchor_backlog)
        # Check from most severe downward
        for state in [DegradationState.FAIL_SAFE,
                      DegradationState.AUDIT_ONLY,
                      DegradationState.OBSERVATION_DROP]:
            thresholds = self._thresholds[state]
            if any(v > t and t > 0 for v, t in zip(values, thresholds)):
                return _STATE_RANK[state]
        return _STATE_RANK[DegradationState.NORMAL]

    def _degradation_reason(self, new_state: DegradationState, m: BackpressureMetrics) -> str:
        parts = []
        thresholds = self._thresholds.get(new_state, (0, 0, 0))
        labels = ("event_bus_lag", "wal_backlog", "anchor_backlog")
        values = (m.event_bus_lag, m.wal_backlog, m.anchor_backlog)
        for label, val, thresh in zip(labels, values, thresholds):
            if thresh > 0 and val > thresh:
                parts.append(f"{label}={val}>{thresh}")
        return f"degraded to {new_state.value}: {', '.join(parts) or 'threshold exceeded'}"

    def _transition(
        self,
        new_state:  DegradationState,
        metrics:    BackpressureMetrics,
        reason:     str,
    ) -> BackpressureTransition:
        """Record and emit a state transition.  Must be called under self._lock."""
        transition = BackpressureTransition(
            from_state=self._state,
            to_state=new_state,
            reason=reason,
            metrics=metrics,
        )
        self._state = new_state
        self._history.append(transition)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        if self._on_transition is not None:
            try:
                self._on_transition(transition)
            except Exception:
                pass
        return transition


# ---------------------------------------------------------------------------
# Factory: build from SecurityConfig
# ---------------------------------------------------------------------------

def from_config(config: object, **kwargs) -> BackpressureManager:
    """
    Convenience factory that reads threshold fields from a SecurityConfig.

    Pass any additional keyword arguments to override config defaults.
    """
    obs = (
        getattr(config, "bp_observation_drop_event_lag", 5_000),
        getattr(config, "bp_observation_drop_wal_backlog", 1_000),
        0,
    )
    aud = (
        getattr(config, "bp_audit_only_event_lag", 8_000),
        getattr(config, "bp_audit_only_wal_backlog", 5_000),
        0,
    )
    fsl = (
        getattr(config, "bp_fail_safe_event_lag", 10_000),
        getattr(config, "bp_fail_safe_wal_backlog", 9_000),
        0,
    )
    hyst = getattr(config, "bp_recovery_hysteresis_seconds", 10.0)
    initial = getattr(config, "initial_degradation_state",
                      DegradationState.NORMAL)
    return BackpressureManager(
        observation_drop_thresholds=obs,
        audit_only_thresholds=aud,
        fail_safe_thresholds=fsl,
        hysteresis_seconds=hyst,
        initial_state=initial,
        **kwargs,
    )
