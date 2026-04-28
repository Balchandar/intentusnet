"""Unit tests for the production CircuitBreaker.

Pins down the CLOSED → OPEN → HALF_OPEN → CLOSED transitions so the demo's
"enforcement decisions" output stays meaningful.
"""

from __future__ import annotations

import time

from intentusnet.security.circuit_breaker_v2 import CircuitBreaker, CircuitState
from intentusnet.security.signals import DecomposedSignalSet


def _signals(*, latency: float = 0.0, error: float = 0.0) -> DecomposedSignalSet:
    """Convenience: build a DecomposedSignalSet for tests."""
    return DecomposedSignalSet(
        latency_signal=latency,
        error_signal=error,
        behavior_signal=0.0,
        policy_signal=0.0,
    )


# ---------------------------------------------------------------------------
# CLOSED → OPEN
# ---------------------------------------------------------------------------


def test_closed_opens_after_failure_threshold():
    cb = CircuitBreaker(failure_threshold=3, timeout_seconds=10.0)
    assert cb.get_state("intent_x") == CircuitState.CLOSED
    assert cb.allow("intent_x") is True

    cb.record("intent_x", _signals(error=0.5), success=False)
    cb.record("intent_x", _signals(error=0.5), success=False)
    # Two failures so far — still closed.
    assert cb.get_state("intent_x") == CircuitState.CLOSED

    cb.record("intent_x", _signals(error=0.9), success=False)
    # Third failure crosses the threshold → OPEN.
    assert cb.get_state("intent_x") == CircuitState.OPEN
    assert cb.allow("intent_x") is False


def test_high_combined_signal_trips_immediately():
    """A single failure with a max-out signal should trip even before the
    failure_threshold is reached."""
    cb = CircuitBreaker(
        failure_threshold=10,
        trip_signal_threshold=0.85,
        timeout_seconds=10.0,
    )
    cb.record("intent_y", _signals(error=1.0), success=False)
    assert cb.get_state("intent_y") == CircuitState.OPEN


def test_success_resets_failure_count():
    """A success in CLOSED state must zero the failure counter."""
    cb = CircuitBreaker(failure_threshold=3, timeout_seconds=10.0)
    cb.record("intent_z", _signals(error=0.5), success=False)
    cb.record("intent_z", _signals(error=0.5), success=False)
    cb.record("intent_z", _signals(), success=True)
    # Failure count reset; two more failures should NOT trip.
    cb.record("intent_z", _signals(error=0.5), success=False)
    cb.record("intent_z", _signals(error=0.5), success=False)
    assert cb.get_state("intent_z") == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# OPEN → HALF_OPEN → CLOSED
# ---------------------------------------------------------------------------


def test_open_transitions_to_half_open_after_timeout():
    cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0.05)
    cb.record("intent_h", _signals(error=1.0), success=False)
    assert cb.get_state("intent_h") == CircuitState.OPEN

    # Before timeout: still OPEN, no probe.
    assert cb.allow("intent_h") is False

    time.sleep(0.06)
    # First call after timeout → probe permitted, state becomes HALF_OPEN.
    assert cb.allow("intent_h") is True
    assert cb.get_state("intent_h") == CircuitState.HALF_OPEN
    # Concurrent probe attempts are rejected.
    assert cb.allow("intent_h") is False


def test_half_open_probe_success_closes_circuit():
    cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0.05)
    cb.record("intent_p", _signals(error=1.0), success=False)
    time.sleep(0.06)
    assert cb.allow("intent_p") is True            # enter HALF_OPEN
    cb.record("intent_p", _signals(), success=True)
    assert cb.get_state("intent_p") == CircuitState.CLOSED
    # New traffic flows immediately.
    assert cb.allow("intent_p") is True


def test_half_open_probe_failure_reopens_circuit():
    cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0.05)
    cb.record("intent_q", _signals(error=1.0), success=False)
    time.sleep(0.06)
    assert cb.allow("intent_q") is True
    cb.record("intent_q", _signals(error=1.0), success=False)
    assert cb.get_state("intent_q") == CircuitState.OPEN


def test_reset_force_closes_circuit():
    cb = CircuitBreaker(failure_threshold=1, timeout_seconds=10.0)
    cb.record("intent_r", _signals(error=1.0), success=False)
    assert cb.get_state("intent_r") == CircuitState.OPEN
    cb.reset("intent_r")
    assert cb.get_state("intent_r") == CircuitState.CLOSED
    assert cb.allow("intent_r") is True


def test_circuits_are_independent_per_intent():
    cb = CircuitBreaker(failure_threshold=1, timeout_seconds=10.0)
    cb.record("intent_a", _signals(error=1.0), success=False)
    assert cb.get_state("intent_a") == CircuitState.OPEN
    assert cb.get_state("intent_b") == CircuitState.CLOSED
    assert cb.allow("intent_b") is True
