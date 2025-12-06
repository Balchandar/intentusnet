from __future__ import annotations
from typing import Protocol, List
import logging
from ..protocol.models import TraceSpan

logger = logging.getLogger("intentusnet.tracing")


class TraceSink(Protocol):
    def record(self, span: TraceSpan) -> None:
        ...


class InMemoryTraceSink:
    def __init__(self) -> None:
        self._spans: List[TraceSpan] = []

    def record(self, span: TraceSpan) -> None:
        self._spans.append(span)
        logger.info(
            "[TRACE] agent=%s intent=%s status=%s latencyMs=%s traceId=%s",
            span.agent,
            span.intent,
            span.status,
            span.latencyMs,
            span.traceId,
        )

    def get_spans(self) -> List[TraceSpan]:
        return list(self._spans)
