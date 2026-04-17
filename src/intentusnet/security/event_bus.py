"""
Security Kernel v2.1 — Unified Security Event Model + In-Process Event Bus

Provides a single observation plane for all security subsystems.  Every
security signal (anomaly, circuit trip, policy violation, state change…) is
emitted as a SecurityEvent so that dashboards, audit logs, and downstream
consumers receive a consistent, ordered stream.

Lamport clock
-------------
The bus maintains a monotonically increasing Lamport clock.  Every emitted
event receives the current clock value BEFORE the counter is incremented, so
events are totally ordered within one process.  Cross-process ordering is out
of scope for Phase 2 (handled by Phase 7 trust anchoring).

Backpressure
------------
The internal queue has a hard cap (``max_queue``).  When the queue is full,
``emit()`` drops the event and increments an internal drop counter rather than
blocking the caller.  The drop count is observable via ``dropped_events``.

Thread safety
-------------
All public methods are thread-safe.  Subscriber dispatch runs on a single
daemon background thread so handlers never block the hot path.
"""

from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

class SecurityEventType(str, Enum):
    # Execution lifecycle
    EXECUTION_STARTED    = "execution_started"
    EXECUTION_COMPLETED  = "execution_completed"
    EXECUTION_FAILED     = "execution_failed"

    # Anomaly detection
    ANOMALY_DETECTED     = "anomaly_detected"

    # Policy
    POLICY_VIOLATION     = "policy_violation"
    RATE_LIMIT_EXCEEDED  = "rate_limit_exceeded"
    IDEMPOTENT_REPLAY    = "idempotent_replay"

    # Capability
    CAPABILITY_VIOLATION = "capability_violation"

    # Circuit breaker
    CIRCUIT_BREAKER_OPENED    = "circuit_breaker_opened"
    CIRCUIT_BREAKER_HALF_OPEN = "circuit_breaker_half_open"
    CIRCUIT_BREAKER_CLOSED    = "circuit_breaker_closed"

    # Kill switch
    KILL_SWITCH_ACTIVATED   = "kill_switch_activated"
    KILL_SWITCH_DEACTIVATED = "kill_switch_deactivated"

    # Degradation / backpressure
    DEGRADATION_STATE_CHANGED = "degradation_state_changed"

    # Side effects
    SIDE_EFFECT_BLOCKED      = "side_effect_blocked"
    SIDE_EFFECT_INTERCEPTED  = "side_effect_intercepted"

    # Trust anchoring
    TRUST_ANCHOR_CONFIRMED = "trust_anchor_confirmed"
    TRUST_ANCHOR_FAILED    = "trust_anchor_failed"

    # Replay
    REPLAY_DIVERGENCE = "replay_divergence"

    # WAL
    WAL_INTEGRITY_FAILURE = "wal_integrity_failure"


# ---------------------------------------------------------------------------
# SecurityEvent
# ---------------------------------------------------------------------------

@dataclass
class SecurityEvent:
    """
    A single security observation.

    ``event_id``      — UUID4, unique per event.
    ``lamport_clock`` — Lamport logical timestamp assigned at emit time.
    ``timestamp``     — wall-clock UTC epoch seconds.
    ``payload``       — arbitrary key-value data; content is event-type-specific.
    """
    event_type:   SecurityEventType
    intent_name:  str
    execution_id: Optional[str]

    lamport_clock: int
    timestamp:     float

    payload: Dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id":     self.event_id,
            "event_type":   self.event_type.value,
            "intent_name":  self.intent_name,
            "execution_id": self.execution_id,
            "lamport_clock": self.lamport_clock,
            "timestamp":    self.timestamp,
            "payload":      self.payload,
        }


# ---------------------------------------------------------------------------
# Subscriber record
# ---------------------------------------------------------------------------

@dataclass
class _Subscriber:
    subscriber_id: str
    event_types:   Set[SecurityEventType]    # empty set = subscribe to all
    handler:       Callable[[SecurityEvent], None]

    def matches(self, event_type: SecurityEventType) -> bool:
        return not self.event_types or event_type in self.event_types


# ---------------------------------------------------------------------------
# SecurityEventBus
# ---------------------------------------------------------------------------

class SecurityEventBus:
    """
    In-process, thread-safe security event dispatcher.

    Usage
    -----
    bus = SecurityEventBus()
    bus.subscribe("my-consumer", {SecurityEventType.ANOMALY_DETECTED}, my_handler)
    bus.emit(SecurityEvent(...))
    bus.stop()          # or use as a context manager

    The bus starts its background dispatcher thread lazily on the first
    ``emit()`` call.  Call ``stop()`` (or use ``with`` context) to shut it
    down cleanly.
    """

    def __init__(self, max_queue: int = 10_000) -> None:
        self._max_queue    = max_queue
        self._queue: queue.Queue[SecurityEvent] = queue.Queue(maxsize=max_queue)
        self._subscribers: Dict[str, _Subscriber] = {}
        self._lamport      = 0
        self._dropped      = 0
        self._lock         = threading.Lock()
        self._running      = False
        self._worker: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Subscriber management
    # ------------------------------------------------------------------

    def subscribe(
        self,
        subscriber_id: str,
        handler: Callable[[SecurityEvent], None],
        event_types: Optional[Set[SecurityEventType]] = None,
    ) -> None:
        """
        Register a handler for security events.

        ``event_types=None`` (or empty set) subscribes to ALL event types.
        Handler is called on the background dispatcher thread — keep it fast.
        """
        with self._lock:
            self._subscribers[subscriber_id] = _Subscriber(
                subscriber_id=subscriber_id,
                event_types=set(event_types) if event_types else set(),
                handler=handler,
            )

    def unsubscribe(self, subscriber_id: str) -> None:
        with self._lock:
            self._subscribers.pop(subscriber_id, None)

    # ------------------------------------------------------------------
    # Emit
    # ------------------------------------------------------------------

    def emit(
        self,
        event_type: SecurityEventType,
        intent_name: str,
        *,
        execution_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> SecurityEvent:
        """
        Create and enqueue a SecurityEvent.

        Assigns the next Lamport clock value atomically.  Non-blocking: if the
        queue is full the event is silently dropped and ``dropped_events`` is
        incremented.

        Returns the created event (even if dropped) so callers can log it.
        """
        with self._lock:
            clock = self._lamport
            self._lamport += 1

        event = SecurityEvent(
            event_type=event_type,
            intent_name=intent_name,
            execution_id=execution_id,
            lamport_clock=clock,
            timestamp=time.time(),
            payload=dict(payload) if payload else {},
        )

        self._ensure_running()

        try:
            self._queue.put_nowait(event)
        except queue.Full:
            with self._lock:
                self._dropped += 1

        return event

    def emit_event(self, event: SecurityEvent) -> None:
        """
        Enqueue a pre-built SecurityEvent (e.g. from another subsystem).

        The event's lamport_clock is NOT overwritten — callers must assign it
        themselves if ordering matters.
        """
        self._ensure_running()
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            with self._lock:
                self._dropped += 1

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    @property
    def dropped_events(self) -> int:
        with self._lock:
            return self._dropped

    @property
    def lamport_clock(self) -> int:
        with self._lock:
            return self._lamport

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _ensure_running(self) -> None:
        with self._lock:
            if not self._running:
                self._running = True
                self._worker = threading.Thread(
                    target=self._dispatch_loop,
                    name="sk-event-bus",
                    daemon=True,
                )
                self._worker.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Drain the queue and stop the background thread."""
        with self._lock:
            if not self._running:
                return
            self._running = False

        if self._worker is not None:
            self._worker.join(timeout=timeout)
            self._worker = None

    def __enter__(self) -> SecurityEventBus:
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # Background dispatcher
    # ------------------------------------------------------------------

    def _dispatch_loop(self) -> None:
        while self._running:
            try:
                event = self._queue.get(timeout=0.05)
            except queue.Empty:
                continue
            self._dispatch(event)

        # Drain remaining events after stop() is called
        while True:
            try:
                event = self._queue.get_nowait()
                self._dispatch(event)
            except queue.Empty:
                break

    def _dispatch(self, event: SecurityEvent) -> None:
        with self._lock:
            subscribers = list(self._subscribers.values())
        for sub in subscribers:
            if sub.matches(event.event_type):
                try:
                    sub.handler(event)
                except Exception:
                    pass   # subscriber errors must never kill the bus thread
