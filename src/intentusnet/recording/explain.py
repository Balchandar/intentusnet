from __future__ import annotations

from typing import Dict, Any
from .models import ExecutionRecord


def explain_record(rec: ExecutionRecord) -> Dict[str, Any]:
    decision = rec.routerDecision or {}
    fallbacks = [e.payload for e in rec.events if e.type == "FALLBACK_TRIGGERED"]
    attempts_end = [e.payload for e in rec.events if e.type == "AGENT_ATTEMPT_END"]
    model_calls = [e.payload for e in rec.events if e.type == "MODEL_CALL"]

    return {
        "executionId": rec.header.executionId,
        "replayable": rec.header.replayable,
        "replayableReason": rec.header.replayableReason,
        "routerDecision": decision,
        "fallbacksTriggered": fallbacks,
        "attempts": attempts_end,
        "modelCallsCount": len(model_calls),
        "finalResponseStatus": (rec.finalResponse or {}).get("status"),
    }
