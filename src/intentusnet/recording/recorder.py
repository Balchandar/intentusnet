from __future__ import annotations

from typing import Protocol, Any, Dict
import threading

from .models import ExecutionRecord, ExecutionEvent, DeterministicClock


class ExecutionRecorder(Protocol):
    def record_router_decision(self, decision_dict: Dict[str, Any]) -> None: ...
    def record_event(self, event_type: str, payload: Dict[str, Any]) -> None: ...
    def record_final_response(self, response_dict: Dict[str, Any]) -> None: ...
    def mark_not_replayable(self, reason: str) -> None: ...
    def get_record(self) -> ExecutionRecord: ...


class InMemoryExecutionRecorder:
    """
    Thread-safe because PARALLEL routing can emit events from multiple threads.
    Deterministic order is still seq-based (not time-based).
    """
    def __init__(self, record: ExecutionRecord) -> None:
        self._record = record
        self._clock = DeterministicClock()
        self._lock = threading.Lock()

    def record_router_decision(self, decision_dict: Dict[str, Any]) -> None:
        with self._lock:
            self._record.routerDecision = decision_dict
        self.record_event("ROUTER_DECISION", decision_dict)

    def record_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._record.events.append(
                ExecutionEvent(seq=self._clock.next(), type=event_type, payload=payload)
            )

    def record_final_response(self, response_dict: Dict[str, Any]) -> None:
        with self._lock:
            self._record.finalResponse = response_dict
        self.record_event("FINAL_RESPONSE", response_dict)

    def mark_not_replayable(self, reason: str) -> None:
        with self._lock:
            self._record.header.replayable = False
            self._record.header.replayableReason = reason

    def get_record(self) -> ExecutionRecord:
        return self._record
