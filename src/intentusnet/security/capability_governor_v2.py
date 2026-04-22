"""
Security Kernel v2.1 — Capability Governor

Suspends capabilities (or whole intents) when the behaviour signal from the
decomposed signal set indicates the agent is operating outside its declared
envelope.

Signal routing
--------------
The governor consumes ONLY ``behavior_signal``.  Latency/error/policy belong to
other subsystems.  This separation prevents a latency spike from flagging a
capability as mis-behaving.

Suspension granularity
----------------------
Two levels are supported:

1. **Per-capability**: when a specific capability is exercised at the moment of
   the breach, only that capability is suspended for the offending intent.
2. **Whole-intent**: when the breach is observed without any capability in
   flight (or when ``exercised_capabilities=None``), the intent itself is
   suspended — subsequent calls to ``is_allowed()`` return False regardless of
   capability.

Persistence & recovery
----------------------
Suspensions are in-memory only.  Operator intervention (``resume`` / ``reset``)
is required to re-enable a capability; they do NOT expire automatically.  This
deliberate conservatism means that a flaky-behaving agent remains blocked until
an operator investigates.

Thread safety
-------------
All public methods are thread-safe.  Event bus emissions happen OUTSIDE the
internal lock to avoid contention with SecurityEventBus's own lock.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .event_bus import SecurityEventBus, SecurityEventType


# ---------------------------------------------------------------------------
# Whole-intent sentinel
# ---------------------------------------------------------------------------

# Marker used in the internal suspended-capabilities set to represent the
# "whole intent is suspended" state.  Chosen to be an identifier that is not a
# legal capability name (leading/trailing double underscores).
_WHOLE_INTENT_MARKER = "__intent__"


# ---------------------------------------------------------------------------
# Suspension event record
# ---------------------------------------------------------------------------

@dataclass
class SuspensionEvent:
    """
    One change to the suspension set.

    ``action`` is either ``"suspend"`` or ``"resume"``.
    ``capability_id`` is the specific capability, or ``None`` when the entire
    intent is suspended.
    ``behavior_signal`` is the signal value observed at the moment of the
    transition (0.0 for manual operator-driven suspend/resume calls).
    """
    intent_name:     str
    capability_id:   Optional[str]
    action:          str
    reason:          str
    behavior_signal: float = 0.0
    timestamp:       float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# CapabilityGovernor
# ---------------------------------------------------------------------------

class CapabilityGovernor:
    """
    Capability-level enforcement based on the behaviour signal.

    Parameters
    ----------
    behavior_threshold
        When a recorded ``behavior_signal >= threshold``, the governor
        suspends the offending capability (or whole intent).
    event_bus
        Optional.  If provided, ``CAPABILITY_VIOLATION`` events are emitted
        on each new suspension (not on resume).
    """

    def __init__(
        self,
        behavior_threshold: float = 0.80,
        event_bus:          Optional[SecurityEventBus] = None,
    ) -> None:
        self._threshold = behavior_threshold
        self._event_bus = event_bus

        # intent_name -> set of suspended capability IDs (plus possibly the
        # _WHOLE_INTENT_MARKER entry for a full-intent suspension).
        self._suspended: Dict[str, Set[str]] = {}
        self._history:   List[SuspensionEvent] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Enforcement: record an observation
    # ------------------------------------------------------------------

    def record(
        self,
        intent_name: str,
        behavior_signal: float,
        *,
        exercised_capabilities: Optional[Iterable[str]] = None,
    ) -> List[str]:
        """
        Evaluate one behaviour signal.

        If the signal is above the threshold, every capability in
        ``exercised_capabilities`` is suspended for this intent.  When the
        iterable is empty or None, the entire intent is suspended.

        Returns the list of capability IDs that were NEWLY suspended by this
        call (empty list when nothing changed or when below threshold).
        The special marker is translated to the original intent name in the
        returned list so callers can log uniformly.
        """
        if behavior_signal < self._threshold:
            return []

        newly_suspended: List[str] = []
        pending_events: List[Tuple[str, Optional[str], str, float]] = []

        targets: List[Optional[str]]
        if exercised_capabilities:
            targets = [c for c in exercised_capabilities if c]
            if not targets:
                targets = [None]   # fall back to whole-intent
        else:
            targets = [None]

        reason = f"behavior_signal={behavior_signal:.3f} >= threshold={self._threshold:.3f}"

        with self._lock:
            current = self._suspended.setdefault(intent_name, set())
            for cap in targets:
                marker = cap if cap is not None else _WHOLE_INTENT_MARKER
                if marker in current:
                    continue
                current.add(marker)
                self._history.append(
                    SuspensionEvent(
                        intent_name=intent_name,
                        capability_id=cap,
                        action="suspend",
                        reason=reason,
                        behavior_signal=behavior_signal,
                    )
                )
                label = cap if cap is not None else intent_name
                newly_suspended.append(label)
                pending_events.append((intent_name, cap, reason, behavior_signal))

        for intent, cap, why, signal in pending_events:
            self._emit(intent, cap, why, signal)

        return newly_suspended

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def is_allowed(
        self,
        intent_name: str,
        capability_id: Optional[str] = None,
    ) -> bool:
        """
        Return True if the capability may execute.

        A capability is blocked if either (a) the whole intent is suspended or
        (b) that specific capability is suspended under the intent.  A call
        without ``capability_id`` is blocked only when the whole intent is
        suspended.
        """
        with self._lock:
            current = self._suspended.get(intent_name)
            if not current:
                return True
            if _WHOLE_INTENT_MARKER in current:
                return False
            if capability_id is None:
                return True
            return capability_id not in current

    def is_intent_suspended(self, intent_name: str) -> bool:
        with self._lock:
            current = self._suspended.get(intent_name)
            return bool(current) and _WHOLE_INTENT_MARKER in current

    def is_capability_suspended(
        self,
        intent_name: str,
        capability_id: str,
    ) -> bool:
        with self._lock:
            current = self._suspended.get(intent_name)
            if not current:
                return False
            return capability_id in current or _WHOLE_INTENT_MARKER in current

    # ------------------------------------------------------------------
    # Manual intervention
    # ------------------------------------------------------------------

    def suspend(
        self,
        intent_name: str,
        capability_id: Optional[str] = None,
        *,
        reason: str = "operator suspend",
    ) -> bool:
        """
        Operator-initiated suspend.  ``capability_id=None`` suspends the whole
        intent.  Returns True if this call changed state.
        """
        changed = False
        with self._lock:
            current = self._suspended.setdefault(intent_name, set())
            marker = capability_id if capability_id is not None else _WHOLE_INTENT_MARKER
            if marker not in current:
                current.add(marker)
                self._history.append(
                    SuspensionEvent(
                        intent_name=intent_name,
                        capability_id=capability_id,
                        action="suspend",
                        reason=reason,
                    )
                )
                changed = True

        if changed:
            self._emit(intent_name, capability_id, reason, 0.0)
        return changed

    def resume(
        self,
        intent_name: str,
        capability_id: Optional[str] = None,
        *,
        reason: str = "operator resume",
    ) -> bool:
        """
        Operator-initiated resume.  Removes a single capability suspension or
        the whole-intent marker.  Returns True if this call changed state.
        """
        changed = False
        with self._lock:
            current = self._suspended.get(intent_name)
            if not current:
                return False
            marker = capability_id if capability_id is not None else _WHOLE_INTENT_MARKER
            if marker in current:
                current.discard(marker)
                self._history.append(
                    SuspensionEvent(
                        intent_name=intent_name,
                        capability_id=capability_id,
                        action="resume",
                        reason=reason,
                    )
                )
                changed = True
            if not current:
                self._suspended.pop(intent_name, None)
        return changed

    def reset(self, intent_name: str) -> None:
        """Clear all suspensions for one intent."""
        with self._lock:
            self._suspended.pop(intent_name, None)

    def reset_all(self) -> None:
        """Clear all suspensions (e.g. after policy reload)."""
        with self._lock:
            self._suspended.clear()

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def get_suspensions(self) -> Dict[str, List[str]]:
        """
        Return a snapshot of all current suspensions.

        The marker for whole-intent suspension is translated to the intent
        name itself so external consumers see a uniform list of strings.
        """
        snapshot: Dict[str, List[str]] = {}
        with self._lock:
            for intent_name, markers in self._suspended.items():
                entries: List[str] = []
                for m in sorted(markers):
                    if m == _WHOLE_INTENT_MARKER:
                        entries.append(intent_name)
                    else:
                        entries.append(m)
                snapshot[intent_name] = entries
        return snapshot

    def suspended_intents(self) -> List[str]:
        """Intents with at least one active suspension."""
        with self._lock:
            return sorted(self._suspended.keys())

    def history(self) -> List[SuspensionEvent]:
        """Return a copy of the suspension history."""
        with self._lock:
            return list(self._history)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _emit(
        self,
        intent_name: str,
        capability_id: Optional[str],
        reason: str,
        behavior_signal: float,
    ) -> None:
        if self._event_bus is None:
            return
        self._event_bus.emit(
            SecurityEventType.CAPABILITY_VIOLATION,
            intent_name,
            payload={
                "capability_id":   capability_id,
                "reason":          reason,
                "behavior_signal": behavior_signal,
                "whole_intent":    capability_id is None,
            },
        )
