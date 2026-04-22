"""
Security Kernel v2.1 — Circuit Breaker

Protects each intent from cascading failures.  Uses the ``latency_signal``
and ``error_signal`` from the decomposed signal set — NOT behavior or policy
signals, which belong to the CapabilityGovernor and PolicyEngine respectively.

State machine
-------------
  CLOSED    → normal operation; failures tracked
  OPEN      → execution blocked; entered after threshold breached
  HALF_OPEN → one probe allowed; transitions to CLOSED or back to OPEN

Transitions
-----------
  CLOSED + failure + (count >= threshold OR combined_signal >= trip_threshold)
      → OPEN immediately
  CLOSED + success
      → reset failure_count
  OPEN + timeout elapsed
      → HALF_OPEN (transition happens lazily in allow(), not on a timer)
  HALF_OPEN + probe success
      → CLOSED; failure_count reset
  HALF_OPEN + probe failure
      → OPEN; opened_at reset

``allow()`` is the enforcement point.  ``record()`` drives state transitions.
Both are thread-safe.  Events are emitted OUTSIDE the lock to avoid contention
with the SecurityEventBus lock.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from .event_bus import SecurityEventBus, SecurityEventType
from .signals import DecomposedSignalSet


# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------

class CircuitState(str, Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"


# ---------------------------------------------------------------------------
# Transition record
# ---------------------------------------------------------------------------

@dataclass
class CircuitTransition:
    intent_name: str
    from_state:  CircuitState
    to_state:    CircuitState
    reason:      str
    timestamp:   float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Per-intent mutable circuit state
# ---------------------------------------------------------------------------

@dataclass
class _IntentCircuit:
    state:            CircuitState = CircuitState.CLOSED
    failure_count:    int          = 0
    opened_at:        Optional[float] = None    # when OPEN was entered
    probe_in_flight:  bool         = False       # HALF_OPEN: probe sent, awaiting result


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """
    Per-intent circuit breaker driven by latency and error signals.

    Parameters
    ----------
    failure_threshold
        Consecutive failures (``success=False``) before opening.
    trip_signal_threshold
        Immediate trip when ``combined_signal >= this`` AND the call failed.
    timeout_seconds
        How long the circuit stays OPEN before moving to HALF_OPEN.
    latency_weight / error_weight
        Weights for combining the two signals.  ``error_weight`` is higher by
        default because errors are a stronger failure indicator.
    event_bus
        If set, state-change events are emitted on each transition.
    on_state_change
        Optional callback: (transition: CircuitTransition) → None.
    """

    def __init__(
        self,
        failure_threshold:    int   = 5,
        trip_signal_threshold: float = 0.85,
        timeout_seconds:      float = 30.0,
        latency_weight:       float = 0.6,
        error_weight:         float = 1.0,
        event_bus:            Optional[SecurityEventBus] = None,
        on_state_change:      Optional[Callable[[CircuitTransition], None]] = None,
    ) -> None:
        self._failure_threshold    = failure_threshold
        self._trip_signal_threshold = trip_signal_threshold
        self._timeout_seconds      = timeout_seconds
        self._latency_weight       = latency_weight
        self._error_weight         = error_weight
        self._event_bus            = event_bus
        self._on_state_change      = on_state_change

        self._circuits: Dict[str, _IntentCircuit] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Enforcement
    # ------------------------------------------------------------------

    def allow(self, intent_name: str) -> bool:
        """
        Return True if a new request for this intent should be executed.

        In HALF_OPEN, exactly ONE probe is allowed at a time.  Subsequent
        calls return False until ``record()`` is called with the probe's
        result.

        Events are emitted outside the lock.
        """
        pending_event: Optional[Tuple] = None
        result: bool

        with self._lock:
            circuit = self._get_or_create(intent_name)
            now = time.time()

            if circuit.state == CircuitState.CLOSED:
                return True

            if circuit.state == CircuitState.OPEN:
                if (circuit.opened_at is not None
                        and (now - circuit.opened_at) >= self._timeout_seconds):
                    transition = self._do_transition(
                        intent_name, circuit,
                        CircuitState.HALF_OPEN,
                        "timeout elapsed, entering half-open probe",
                    )
                    pending_event = (
                        SecurityEventType.CIRCUIT_BREAKER_HALF_OPEN,
                        intent_name, transition,
                    )
                    circuit.probe_in_flight = True
                    result = True
                else:
                    return False
            elif circuit.state == CircuitState.HALF_OPEN:
                if not circuit.probe_in_flight:
                    circuit.probe_in_flight = True
                    result = True
                else:
                    return False
            else:
                return True

        self._maybe_emit(pending_event)
        return result

    # ------------------------------------------------------------------
    # Signal recording
    # ------------------------------------------------------------------

    def record(
        self,
        intent_name: str,
        signals:     Optional[DecomposedSignalSet],
        *,
        success:     bool,
    ) -> CircuitState:
        """
        Record one execution outcome and update circuit state.

        Returns the NEW circuit state after any transitions.
        """
        combined = self._combined_signal(signals) if signals is not None else 0.0
        pending_event: Optional[Tuple] = None

        with self._lock:
            circuit = self._get_or_create(intent_name)

            if circuit.state == CircuitState.CLOSED:
                if success:
                    circuit.failure_count = 0
                else:
                    circuit.failure_count += 1
                    should_trip = (
                        circuit.failure_count >= self._failure_threshold
                        or combined >= self._trip_signal_threshold
                    )
                    if should_trip:
                        transition = self._do_transition(
                            intent_name, circuit, CircuitState.OPEN,
                            reason=(
                                f"failures={circuit.failure_count} "
                                f"combined_signal={combined:.3f}"
                            ),
                        )
                        pending_event = (
                            SecurityEventType.CIRCUIT_BREAKER_OPENED,
                            intent_name, transition,
                        )

            elif circuit.state == CircuitState.HALF_OPEN:
                circuit.probe_in_flight = False
                if success:
                    circuit.failure_count = 0
                    transition = self._do_transition(
                        intent_name, circuit, CircuitState.CLOSED,
                        reason="probe succeeded, circuit closed",
                    )
                    pending_event = (
                        SecurityEventType.CIRCUIT_BREAKER_CLOSED,
                        intent_name, transition,
                    )
                else:
                    circuit.failure_count += 1
                    transition = self._do_transition(
                        intent_name, circuit, CircuitState.OPEN,
                        reason="probe failed, circuit re-opened",
                    )
                    pending_event = (
                        SecurityEventType.CIRCUIT_BREAKER_OPENED,
                        intent_name, transition,
                    )

            # In OPEN state: execution should not have run.  We still update
            # failure_count so we know it happened.
            elif circuit.state == CircuitState.OPEN and not success:
                circuit.failure_count += 1

            new_state = circuit.state

        self._maybe_emit(pending_event)
        return new_state

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_state(self, intent_name: str) -> CircuitState:
        with self._lock:
            return self._get_or_create(intent_name).state

    def known_intents(self) -> List[str]:
        with self._lock:
            return list(self._circuits.keys())

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def reset(self, intent_name: str) -> None:
        """Force-reset a circuit to CLOSED (e.g. operator override)."""
        pending_event: Optional[Tuple] = None
        with self._lock:
            circuit = self._circuits.get(intent_name)
            if circuit and circuit.state != CircuitState.CLOSED:
                transition = self._do_transition(
                    intent_name, circuit, CircuitState.CLOSED,
                    reason="operator reset",
                )
                pending_event = (
                    SecurityEventType.CIRCUIT_BREAKER_CLOSED,
                    intent_name, transition,
                )
            elif circuit:
                circuit.failure_count = 0
        self._maybe_emit(pending_event)

    def reset_all(self) -> None:
        """Reset all circuits."""
        with self._lock:
            for name, circuit in self._circuits.items():
                circuit.state         = CircuitState.CLOSED
                circuit.failure_count = 0
                circuit.opened_at     = None
                circuit.probe_in_flight = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create(self, intent_name: str) -> _IntentCircuit:
        if intent_name not in self._circuits:
            self._circuits[intent_name] = _IntentCircuit()
        return self._circuits[intent_name]

    def _do_transition(
        self,
        intent_name: str,
        circuit:     _IntentCircuit,
        new_state:   CircuitState,
        reason:      str,
    ) -> CircuitTransition:
        transition = CircuitTransition(
            intent_name=intent_name,
            from_state=circuit.state,
            to_state=new_state,
            reason=reason,
        )
        circuit.state = new_state
        if new_state == CircuitState.OPEN:
            circuit.opened_at     = time.time()
            circuit.probe_in_flight = False
        elif new_state == CircuitState.CLOSED:
            circuit.opened_at     = None
            circuit.probe_in_flight = False
        if self._on_state_change:
            try:
                self._on_state_change(transition)
            except Exception:
                pass
        return transition

    def _combined_signal(self, signals: DecomposedSignalSet) -> float:
        return max(
            signals.latency_signal * self._latency_weight,
            signals.error_signal   * self._error_weight,
        )

    def _maybe_emit(self, pending: Optional[Tuple]) -> None:
        if pending is None or self._event_bus is None:
            return
        event_type, intent_name, transition = pending
        self._event_bus.emit(
            event_type,
            intent_name,
            payload={
                "from_state": transition.from_state.value,
                "to_state":   transition.to_state.value,
                "reason":     transition.reason,
            },
        )
