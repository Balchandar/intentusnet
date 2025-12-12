from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from intentusnet.protocol.tracing import TraceSpan


class TraceSink(ABC):
    """
    Abstraction for recording trace spans produced by the router.

    Implementations can:
    - keep spans in memory (for demos, tests)
    - forward spans to OpenTelemetry exporters
    - send spans to logs, Kafka, etc.
    """

    @abstractmethod
    def record(self, span: TraceSpan) -> None:
        """
        Persist or export a single trace span.
        """
        raise NotImplementedError

    def get_spans(self) -> List[TraceSpan]:
        """
        Optional: return all spans if the implementation is span-backed.

        The default implementation raises to signal that not all sinks
        need to support retrieval (e.g., OTEL-only).
        """
        raise NotImplementedError("This TraceSink does not support get_spans()")


class InMemoryTraceSink(TraceSink):
    """
    Simple in-memory trace sink.

    Intended for:
    - local development
    - unit/integration tests
    - interactive demos (print a trace table, etc.)
    """

    def __init__(self) -> None:
        self._spans: List[TraceSpan] = []

    def record(self, span: TraceSpan) -> None:
        self._spans.append(span)

    def get_spans(self) -> List[TraceSpan]:
        # Return a copy to avoid accidental external mutation
        return list(self._spans)

    def clear(self) -> None:
        """
        Remove all stored spans.
        Useful between tests or demo runs.
        """
        self._spans.clear()
