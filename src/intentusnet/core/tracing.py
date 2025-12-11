from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List
import time
import uuid


# ----------------------------------------------------------------------
# TRACE SPAN DATA MODEL (FINAL)
# ----------------------------------------------------------------------
@dataclass
class TraceSpan:
    """
    Represents a single recorded event in the runtime.
    Core fields are minimal. 
    Demo-friendly accessors are provided for compatibility.
    """
    id: str
    traceId: str
    name: str
    startTime: str
    endTime: str
    attributes: Dict[str, Any] = field(default_factory=dict)

    # --- Compatibility properties for pretty printing in demo ----

    @property
    def agent(self) -> str:
        return self.attributes.get("agent", "")

    @property
    def intent(self) -> str:
        return self.attributes.get("intent", "")

    @property
    def latencyMs(self) -> int:
        return self.attributes.get("latencyMs", 0)

    @property
    def status(self) -> str:
        return self.attributes.get("status", "")

    @property
    def error(self) -> str:
        return self.attributes.get("error", "")


# ----------------------------------------------------------------------
# GENERIC TRACE SINK INTERFACE
# ----------------------------------------------------------------------
class TraceSink:
    def record(self, traceId: str, span: Dict[str, Any]) -> None:
        raise NotImplementedError

    def get_spans(self) -> List[TraceSpan]:
        raise NotImplementedError

    def get_trace(self, traceId: str) -> List[TraceSpan]:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError


# ----------------------------------------------------------------------
# INTENTUSNET TRACER (REAL IMPLEMENTATION)
# ----------------------------------------------------------------------
class IntentusNetTracer(TraceSink):
    """
    Simple in-memory tracer compatible with TraceSink.
    Stores TraceSpan objects and allows query by traceId.
    """

    def __init__(self):
        self._spans: List[TraceSpan] = []

    def _now_iso(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def record(self, traceId: str, span: Dict[str, Any]) -> None:
        s = TraceSpan(
            id=span.get("id", str(uuid.uuid4())),
            traceId=traceId,
            name=span.get("name", "unknown"),
            startTime=span.get("start", self._now_iso()),
            endTime=span.get("end", self._now_iso()),
            attributes=span.get("attributes", {}),
        )
        self._spans.append(s)

    def get_spans(self) -> List[TraceSpan]:
        return list(self._spans)

    def get_trace(self, traceId: str) -> List[TraceSpan]:
        return [s for s in self._spans if s.traceId == traceId]

    def clear(self) -> None:
        self._spans.clear()


# ----------------------------------------------------------------------
# ALIAS FOR BACKWARD COMPATIBILITY
# ----------------------------------------------------------------------
class InMemoryTraceSink(IntentusNetTracer):
    pass
