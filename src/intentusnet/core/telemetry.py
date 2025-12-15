from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .settings import get_settings

logger = logging.getLogger("intentusnet.telemetry")


@dataclass
class TelemetrySpan:
    trace_id: str
    intent: str
    agent: str
    latency_ms: int
    success: bool
    error_code: Optional[str] = None


class Telemetry:
    """
    Thin abstraction for metrics and tracing.

    - Uses OpenTelemetry if configured (future)
    - Otherwise falls back to logging-based metrics
    """

    def __init__(self) -> None:
        self._settings = get_settings()

        # NOTE: this is telemetry backend, NOT router trace sink
        self._backend = (
            getattr(self._settings.runtime, "telemetry_backend", None)
            or getattr(self._settings.runtime, "trace_sink", "memory")
        ).lower()

        self._log = logger
        self._otel_available = False  # future

    # --------------------------------------------------------------
    # Metrics
    # --------------------------------------------------------------
    def record_request(
        self,
        *,
        intent: str,
        agent: str,
        success: bool,
        latency_ms: int,
        tenant: Optional[str] = None,
        subject: Optional[str] = None,
        error_code: Optional[str] = None,
    ) -> None:
        """
        Record a single routing/agent request metric.
        """
        if self._backend in ("stdout", "stdout-json"):
            self._log.info(
                "metrics.intent_request %s",
                {
                    "intent": intent,
                    "agent": agent,
                    "success": success,
                    "latency_ms": latency_ms,
                    "tenant": tenant,
                    "subject": subject,
                    "error_code": error_code,
                },
            )
        else:
            # No-op baseline for v1
            pass

    # --------------------------------------------------------------
    # Tracing hook (optional)
    # --------------------------------------------------------------
    def record_span(self, span: TelemetrySpan) -> None:
        if self._backend in ("stdout", "stdout-json"):
            self._log.debug(
                "trace.span %s",
                {
                    "trace_id": span.trace_id,
                    "intent": span.intent,
                    "agent": span.agent,
                    "latency_ms": span.latency_ms,
                    "success": span.success,
                    "error_code": span.error_code,
                },
            )
        else:
            pass


# Shared singleton-style telemetry
_telemetry_instance: Optional[Telemetry] = None


def get_telemetry() -> Telemetry:
    global _telemetry_instance
    if _telemetry_instance is None:
        _telemetry_instance = Telemetry()
    return _telemetry_instance
