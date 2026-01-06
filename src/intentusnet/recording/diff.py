from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List
from .models import ExecutionRecord


def diff_records(a: ExecutionRecord, b: ExecutionRecord) -> Dict[str, Any]:
    return {
        "executionA": a.header.executionId,
        "executionB": b.header.executionId,
        "envelopeHashA": a.header.envelopeHash,
        "envelopeHashB": b.header.envelopeHash,
        "routerDecisionChanged": a.routerDecision != b.routerDecision,
        "finalResponseChanged": a.finalResponse != b.finalResponse,
        "fallbackEventsA": [e.payload for e in a.events if e.type == "FALLBACK_TRIGGERED"],
        "fallbackEventsB": [e.payload for e in b.events if e.type == "FALLBACK_TRIGGERED"],
        "modelCallsA": [e.payload for e in a.events if e.type == "MODEL_CALL"],
        "modelCallsB": [e.payload for e in b.events if e.type == "MODEL_CALL"],
    }


@dataclass
class ExecutionDiff:
    """
    Diff between two executions.
    """
    execution_id_1: str
    execution_id_2: str
    envelope_same: bool
    router_decision_same: bool
    final_response_same: bool
    event_count_1: int
    event_count_2: int
    differences: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id_1": self.execution_id_1,
            "execution_id_2": self.execution_id_2,
            "envelope_same": self.envelope_same,
            "router_decision_same": self.router_decision_same,
            "final_response_same": self.final_response_same,
            "event_count_1": self.event_count_1,
            "event_count_2": self.event_count_2,
            "differences": self.differences,
        }


class ExecutionDiffer:
    """
    Compare two execution records.
    """

    def diff(self, record1: ExecutionRecord, record2: ExecutionRecord) -> ExecutionDiff:
        """
        Compare two execution records and return differences.
        """
        differences = []

        # Compare envelopes
        envelope_same = record1.envelope == record2.envelope
        if not envelope_same:
            differences.append("Envelopes differ")

        # Compare router decisions
        router_decision_same = record1.routerDecision == record2.routerDecision
        if not router_decision_same:
            differences.append("Router decisions differ")

        # Compare final responses
        final_response_same = record1.finalResponse == record2.finalResponse
        if not final_response_same:
            differences.append("Final responses differ")

        # Compare event counts
        event_count_1 = len(record1.events)
        event_count_2 = len(record2.events)
        if event_count_1 != event_count_2:
            differences.append(f"Event counts differ: {event_count_1} vs {event_count_2}")

        # Compare envelope hashes
        if record1.header.envelopeHash != record2.header.envelopeHash:
            differences.append("Envelope hashes differ")

        # Compare replayability
        if record1.header.replayable != record2.header.replayable:
            differences.append("Replayability differs")

        return ExecutionDiff(
            execution_id_1=record1.header.executionId,
            execution_id_2=record2.header.executionId,
            envelope_same=envelope_same,
            router_decision_same=router_decision_same,
            final_response_same=final_response_same,
            event_count_1=event_count_1,
            event_count_2=event_count_2,
            differences=differences,
        )
