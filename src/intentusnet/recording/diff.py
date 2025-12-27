from __future__ import annotations

from typing import Dict, Any
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
