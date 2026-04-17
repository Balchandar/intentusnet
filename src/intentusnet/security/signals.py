"""
Security Kernel v2.1 — Decomposed Signal Computation

Separates a raw execution observation into four independent signals so that
consumers (CircuitBreaker, CapabilityGovernor, FingerprintEngine, PolicyEngine)
only react to the signals they own.  This prevents correlated false positives
where a single anomalous event triggers every defence simultaneously.

Signal decomposition
--------------------
  latency_signal   → fed to CircuitBreaker + FingerprintEngine
  error_signal     → fed to CircuitBreaker
  behavior_signal  → fed to CapabilityGovernor + FingerprintEngine
  policy_signal    → fed to PolicyEngine audit only

Each signal is a float in [0.0, 1.0].

Dual-baseline EWMA
------------------
Short-term baseline (α = 0.10) tracks recent spikes.
Long-term  baseline (α = 0.01) tracks slow drift.

drift_score = clamp((short – long) / long, 0, 1)  when long > 0

When drift_score >= 0.5 the baselines are frozen (not updated) so that a
sustained attack cannot poison the learned baseline.

Sigmoid scoring
---------------
    signal = 1 / (1 + exp(-k * (raw - midpoint)))

k=10 gives a sharp transition at midpoint.  midpoint is the anomaly threshold
for that dimension.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Dual-baseline EWMA state  (one per intent × dimension)
# ---------------------------------------------------------------------------

_SHORT_ALPHA = 0.10   # reacts to spikes within ~10 samples
_LONG_ALPHA  = 0.01   # reacts to drift within ~100 samples
_DRIFT_FREEZE_THRESHOLD = 0.50   # freeze baselines above this drift score


@dataclass
class DualBaselineResult:
    """Snapshot returned by EWMABaseline.update()."""
    short_ema: float
    long_ema: float
    drift_score: float          # 0.0 = no drift; 1.0 = maximum drift
    baseline_frozen: bool       # True when drift_score >= freeze threshold
    z_score: Optional[float]    # (value - short_ema) / short_stddev; None if insufficient data


class _EWMAState:
    """Thread-safe dual-baseline EWMA for a single time series."""

    __slots__ = (
        "_short_ema", "_long_ema",
        "_short_var",           # running variance estimate (short baseline only)
        "_n",                   # number of samples seen
        "_lock",
    )

    def __init__(self) -> None:
        self._short_ema: float = 0.0
        self._long_ema:  float = 0.0
        self._short_var: float = 0.0    # Welford-style EWMA variance
        self._n: int = 0
        self._lock = threading.Lock()

    def update(self, value: float) -> DualBaselineResult:
        with self._lock:
            self._n += 1
            if self._n == 1:
                # Initialise both baselines to first observation
                self._short_ema = value
                self._long_ema  = value
                self._short_var = 0.0
                return DualBaselineResult(
                    short_ema=self._short_ema,
                    long_ema=self._long_ema,
                    drift_score=0.0,
                    baseline_frozen=False,
                    z_score=None,
                )

            drift_score = self._compute_drift()

            z: Optional[float] = None
            if self._short_var > 0:
                z = (value - self._short_ema) / math.sqrt(self._short_var)

            if drift_score < _DRIFT_FREEZE_THRESHOLD:
                self._short_ema = _SHORT_ALPHA * value + (1 - _SHORT_ALPHA) * self._short_ema
                self._long_ema  = _LONG_ALPHA  * value + (1 - _LONG_ALPHA)  * self._long_ema
                delta = value - self._short_ema
                self._short_var = (1 - _SHORT_ALPHA) * (self._short_var + _SHORT_ALPHA * delta * delta)

            drift_score_after = self._compute_drift()
            frozen = drift_score_after >= _DRIFT_FREEZE_THRESHOLD

            return DualBaselineResult(
                short_ema=self._short_ema,
                long_ema=self._long_ema,
                drift_score=drift_score_after,
                baseline_frozen=frozen,
                z_score=z,
            )

    def _compute_drift(self) -> float:
        if self._long_ema <= 0:
            return 0.0
        raw = (self._short_ema - self._long_ema) / self._long_ema
        return max(0.0, min(1.0, raw))

    def peek(self) -> DualBaselineResult:
        with self._lock:
            drift = self._compute_drift()
            return DualBaselineResult(
                short_ema=self._short_ema,
                long_ema=self._long_ema,
                drift_score=drift,
                baseline_frozen=drift >= _DRIFT_FREEZE_THRESHOLD,
                z_score=None,
            )


# ---------------------------------------------------------------------------
# Four-signal decomposition result
# ---------------------------------------------------------------------------

@dataclass
class DecomposedSignalSet:
    """
    The four independent signals produced by ``compute()``.

    Each signal is a float in [0.0, 1.0].  Higher = more anomalous.

    Consumers
    ---------
      latency_signal  → CircuitBreaker, FingerprintEngine
      error_signal    → CircuitBreaker
      behavior_signal → CapabilityGovernor, FingerprintEngine
      policy_signal   → PolicyEngine / ForensicAuditLog (audit only)

    Also carries the dual-baseline diagnostic for the latency dimension.
    """
    latency_signal:  float
    error_signal:    float
    behavior_signal: float
    policy_signal:   float

    # Diagnostics — may be None if baselines are not yet warm
    latency_baseline: Optional[DualBaselineResult] = None

    @property
    def max_signal(self) -> float:
        return max(self.latency_signal, self.error_signal,
                   self.behavior_signal, self.policy_signal)

    def to_dict(self) -> Dict[str, float]:
        return {
            "latency_signal":  round(self.latency_signal,  4),
            "error_signal":    round(self.error_signal,    4),
            "behavior_signal": round(self.behavior_signal, 4),
            "policy_signal":   round(self.policy_signal,   4),
            "max_signal":      round(self.max_signal,      4),
        }


# ---------------------------------------------------------------------------
# Registry of per-intent EWMA baselines
# ---------------------------------------------------------------------------

class _BaselineRegistry:
    """Thread-safe registry mapping (intent_name, dimension) → _EWMAState."""

    def __init__(self) -> None:
        self._states: Dict[tuple, _EWMAState] = {}
        self._lock = threading.Lock()

    def get_or_create(self, intent: str, dimension: str) -> _EWMAState:
        key = (intent, dimension)
        with self._lock:
            if key not in self._states:
                self._states[key] = _EWMAState()
            return self._states[key]

    def reset_intent(self, intent: str) -> None:
        with self._lock:
            keys = [k for k in self._states if k[0] == intent]
            for k in keys:
                del self._states[k]


# Module-level shared registry (singleton per process).
_registry = _BaselineRegistry()


# ---------------------------------------------------------------------------
# Sigmoid helper
# ---------------------------------------------------------------------------

def _sigmoid(raw: float, midpoint: float, k: float = 10.0) -> float:
    """Map raw value to [0, 1] with a sigmoid centred at midpoint."""
    try:
        return 1.0 / (1.0 + math.exp(-k * (raw - midpoint)))
    except OverflowError:
        return 1.0 if raw > midpoint else 0.0


# ---------------------------------------------------------------------------
# Public compute() function
# ---------------------------------------------------------------------------

def compute(
    intent_name: str,
    *,
    # Latency dimension
    latency_ms: float,
    latency_anomaly_threshold_ms: float = 500.0,
    # Error dimension
    error_occurred: bool = False,
    consecutive_errors: int = 0,
    error_threshold: int = 3,
    # Behavior dimension
    unexpected_capabilities: int = 0,
    policy_violations: int = 0,
    behavior_threshold: int = 1,
    # Policy dimension
    policy_score: float = 0.0,       # 0.0–1.0 from PolicyEngine, if available
    # Baseline registry (override for testing)
    registry: Optional[_BaselineRegistry] = None,
) -> DecomposedSignalSet:
    """
    Compute the four-signal decomposition for one execution observation.

    This function is a pure transformation: it updates EWMA baselines and
    returns a ``DecomposedSignalSet``.  It has no side-effects beyond
    mutating the in-memory EWMA states in ``_registry``.

    Parameters
    ----------
    intent_name
        Identifies which EWMA baseline to update.
    latency_ms
        Wall-clock execution latency in milliseconds.
    latency_anomaly_threshold_ms
        The latency at which the sigmoid midpoint sits (default 500 ms).
    error_occurred
        Whether the execution ended in an error/exception.
    consecutive_errors
        Number of consecutive errors on this intent up to and including now.
    error_threshold
        Number of consecutive errors that map to signal = 0.5.
    unexpected_capabilities
        Count of capabilities exercised that were not declared in the registry.
    policy_violations
        Count of policy rules violated during execution.
    behavior_threshold
        Count that maps to behavior_signal = 0.5.
    policy_score
        Optional pre-computed policy signal (0.0–1.0) from the PolicyEngine.
    registry
        Internal override for tests; pass None to use the module-level registry.
    """
    reg = registry if registry is not None else _registry

    # --- Latency signal ---
    lat_state = reg.get_or_create(intent_name, "latency")
    lat_baseline = lat_state.update(latency_ms)

    # Use z-score relative to short-baseline if baseline is warm;
    # fall back to absolute threshold via sigmoid.
    if lat_baseline.z_score is not None and lat_baseline.short_ema > 0:
        # z normalised by sigmoid: z=0 → 0.5, z=4 → ~0.98
        raw_lat = max(0.0, lat_baseline.z_score)
        latency_signal = _sigmoid(raw_lat, midpoint=2.0, k=1.0)
        # Suppress if drift is freezing baselines (baseline may be stale)
        if lat_baseline.baseline_frozen:
            latency_signal *= 0.5
    else:
        latency_signal = _sigmoid(latency_ms, midpoint=latency_anomaly_threshold_ms, k=0.01)

    # --- Error signal ---
    # Binary component + cumulative component via sigmoid
    binary_err = 1.0 if error_occurred else 0.0
    cumul_err  = _sigmoid(float(consecutive_errors), midpoint=float(error_threshold), k=1.0)
    error_signal = max(binary_err * 0.4, cumul_err)

    # --- Behavior signal ---
    combined_behav = float(unexpected_capabilities + policy_violations)
    behavior_signal = _sigmoid(combined_behav, midpoint=float(behavior_threshold), k=2.0)

    # --- Policy signal ---
    # Clamp externally provided score to [0, 1]
    policy_signal = max(0.0, min(1.0, policy_score))

    return DecomposedSignalSet(
        latency_signal=round(max(0.0, min(1.0, latency_signal)), 6),
        error_signal=round(max(0.0, min(1.0, error_signal)), 6),
        behavior_signal=round(max(0.0, min(1.0, behavior_signal)), 6),
        policy_signal=round(max(0.0, min(1.0, policy_signal)), 6),
        latency_baseline=lat_baseline,
    )


def reset_intent_baselines(intent_name: str) -> None:
    """Clear all EWMA state for an intent (e.g. after a deployment)."""
    _registry.reset_intent(intent_name)
