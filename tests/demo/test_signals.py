"""Unit tests for the decomposed signal computation in
``intentusnet.security.signals``.

These tests pin down two contracts that the demo depends on:

1. The four signals are independent — exercising one dimension does not
   bleed into the others.
2. The dual-baseline EWMA reacts faster to spikes (short baseline) than
   to slow drift (long baseline), and a spike eventually scores higher
   than a steady stream of normal samples.
"""

from __future__ import annotations

import pytest

from intentusnet.security.signals import (
    DecomposedSignalSet,
    _BaselineRegistry,
    compute,
    reset_intent_baselines,
)


@pytest.fixture
def fresh_registry() -> _BaselineRegistry:
    """Each test gets an isolated baseline registry so EWMA state from one
    test does not leak into another."""
    return _BaselineRegistry()


def _warm(reg: _BaselineRegistry, intent: str, latency_ms: float, n: int) -> DecomposedSignalSet:
    """Push ``n`` samples at the same latency so the baselines settle."""
    last: DecomposedSignalSet | None = None
    for _ in range(n):
        last = compute(intent, latency_ms=latency_ms, registry=reg)
    assert last is not None
    return last


# ---------------------------------------------------------------------------
# Independence
# ---------------------------------------------------------------------------


def test_error_signal_does_not_affect_latency_signal(fresh_registry):
    """An isolated error must not raise the latency signal."""
    _warm(fresh_registry, "intent_a", latency_ms=20.0, n=20)
    sig = compute(
        "intent_a",
        latency_ms=20.0,
        error_occurred=True,
        consecutive_errors=5,
        registry=fresh_registry,
    )
    assert sig.error_signal > 0.4
    assert sig.latency_signal < 0.2


def test_behavior_signal_does_not_affect_error_signal(fresh_registry):
    """Capability/policy violations are routed to ``behavior_signal``
    only — ``error_signal`` must stay flat when no error occurred."""
    baseline = compute("intent_b", latency_ms=20.0, registry=fresh_registry)
    with_behaviour = compute(
        "intent_b",
        latency_ms=20.0,
        unexpected_capabilities=2,
        policy_violations=1,
        registry=fresh_registry,
    )
    assert with_behaviour.behavior_signal > 0.5
    # The error channel has a small sigmoid floor at zero consecutive
    # errors; the contract is that exercising the behaviour dimension
    # does not move that floor.
    assert with_behaviour.error_signal == pytest.approx(baseline.error_signal, abs=1e-9)


def test_policy_signal_is_clamped(fresh_registry):
    """``policy_score`` is opaque, supplied externally; it must be clamped
    into [0, 1]."""
    sig_low = compute("intent_c", latency_ms=10.0, policy_score=-2.0, registry=fresh_registry)
    sig_high = compute("intent_c", latency_ms=10.0, policy_score=5.0, registry=fresh_registry)
    assert sig_low.policy_signal == 0.0
    assert sig_high.policy_signal == 1.0


# ---------------------------------------------------------------------------
# EWMA short vs long baseline
# ---------------------------------------------------------------------------


def test_short_baseline_reacts_to_spike_after_steady_state(fresh_registry):
    """After the baselines are warm at a low latency, a single 10× spike
    must produce a higher latency_signal than the steady state did."""
    steady = _warm(fresh_registry, "intent_d", latency_ms=20.0, n=30)
    spike = compute("intent_d", latency_ms=200.0, registry=fresh_registry)
    assert spike.latency_signal > steady.latency_signal
    # Sanity: steady state is essentially noise-floor.
    assert steady.latency_signal < 0.2


def test_long_baseline_drifts_more_slowly_than_short(fresh_registry):
    """Push a steady high-latency stream. The short baseline should have
    moved more than the long baseline after a small number of samples."""
    intent = "intent_e"
    _warm(fresh_registry, intent, latency_ms=20.0, n=50)
    # Now drift up to 80 ms steadily.
    last = None
    for _ in range(20):
        last = compute(intent, latency_ms=80.0, registry=fresh_registry)
    assert last is not None
    assert last.latency_baseline is not None
    assert last.latency_baseline.short_ema > last.latency_baseline.long_ema


def test_consecutive_errors_drive_signal_up_monotonically(fresh_registry):
    """The error signal should rise monotonically as consecutive errors
    accumulate."""
    history = []
    for k in range(0, 8):
        sig = compute(
            "intent_f",
            latency_ms=20.0,
            error_occurred=True,
            consecutive_errors=k,
            registry=fresh_registry,
        )
        history.append(sig.error_signal)
    # Allow a tiny epsilon for floating point: the sequence should never
    # decrease.
    for prev, nxt in zip(history, history[1:]):
        assert nxt + 1e-9 >= prev


def test_signals_are_in_unit_interval(fresh_registry):
    """All four signals are guaranteed to be in [0, 1]."""
    for latency in (1.0, 100.0, 5_000.0):
        sig = compute("intent_g", latency_ms=latency, error_occurred=True, registry=fresh_registry)
        for value in sig.to_dict().values():
            assert 0.0 <= value <= 1.0


def test_reset_clears_baselines():
    """``reset_intent_baselines`` empties module-level state for an intent."""
    compute("intent_h", latency_ms=20.0)
    compute("intent_h", latency_ms=20.0)
    reset_intent_baselines("intent_h")
    # After reset the next sample must initialise a brand-new baseline,
    # which means drift_score is exactly 0 on the first sample.
    sig = compute("intent_h", latency_ms=20.0)
    assert sig.latency_baseline is not None
    assert sig.latency_baseline.drift_score == 0.0
