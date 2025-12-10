# intentusnet/tracing.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List
import time
import uuid


# ----------------------------------------------------------------------
# TRACE SPAN DATA MODEL
# ----------------------------------------------------------------------

@dataclass
class TraceSpan:
    """
    Represents a single recorded event in the runtime.
    """
    id: str
    traceId: str
    name: str
    startTime: str
    endTime: str
    attributes: Dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------
# LIGHTWEIGHT TRACER
# ----------------------------------------------------------------------

class IntentusNetTracer:
    """
    Simple in-memory tracer for IntentusNet Router, Agents,
    Orchestrator, and Transports.

    - No external dependencies (no OpenTelemetry unless you want)
    - Easy to display in console or UI
    - Works across distributed steps because of traceId
    """

    def __init__(self):
        self._spans: List[TraceSpan] = []

    # ------------------------------------------------------------------
    def _now_iso(self) -> str:
        """Return current time in ISO8601 format."""
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # ------------------------------------------------------------------
    def record(self, traceId: str, span: Dict[str, Any]) -> None:
        """
        Convert router/orchestrator/transport span dict to TraceSpan object.
        """
        s = TraceSpan(
            id=span.get("id", str(uuid.uuid4())),
            traceId=traceId,
            name=span.get("name", "unknown"),
            startTime=span.get("start", self._now_iso()),
            endTime=span.get("end", self._now_iso()),
            attributes=span.get("attributes", {}),
        )
        self._spans.append(s)

    # ------------------------------------------------------------------
    def get_spans(self) -> List[TraceSpan]:
        """Return all spans collected so far."""
        return list(self._spans)

    # ------------------------------------------------------------------
    def get_trace(self, traceId: str) -> List[TraceSpan]:
        """
        Get spans for a specific traceId (router + workflow steps).
        """
        return [s for s in self._spans if s.traceId == traceId]

    # ------------------------------------------------------------------
    def clear(self) -> None:
        """Reset tracer (used in testing)."""
        self._spans.clear()
