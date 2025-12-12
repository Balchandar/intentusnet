from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable, Optional

from intentusnet.protocol.intent import IntentEnvelope
from intentusnet.protocol.response import AgentResponse, ErrorInfo
from .telemetry import get_telemetry


@runtime_checkable
class RouterMiddleware(Protocol):
    """
    Pluggable middleware for IntentRouter.

    Lifecycle:
      - before_route(env)
      - after_route(env, response)
      - on_error(env, error)
    """

    def before_route(self, env: IntentEnvelope) -> None:  # pragma: no cover - interface
        ...

    def after_route(self, env: IntentEnvelope, response: AgentResponse) -> None:  # pragma: no cover - interface
        ...

    def on_error(self, env: IntentEnvelope, error: ErrorInfo) -> None:  # pragma: no cover - interface
        ...


class LoggingRouterMiddleware:
    """
    Simple logging middleware to demonstrate the concept.
    """

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or logging.getLogger("intentusnet.router")

    def before_route(self, env: IntentEnvelope) -> None:
        trace_id = getattr(env.metadata, "traceId", None)
        self._log.debug(
            "Routing intent '%s' (traceId=%s, targetAgent=%s, strategy=%s)",
            env.intent.name,
            trace_id,
            getattr(env.routing, "targetAgent", None),
            getattr(env.routing, "strategy", None),
        )

    def after_route(self, env: IntentEnvelope, response: AgentResponse) -> None:
        trace_id = getattr(env.metadata, "traceId", None)
        if response.error:
            self._log.info(
                "Intent '%s' completed WITH error (traceId=%s, agent=%s, code=%s)",
                env.intent.name,
                trace_id,
                response.metadata.get("agent"),
                response.error.code,
            )
        else:
            self._log.info(
                "Intent '%s' completed OK (traceId=%s, agent=%s)",
                env.intent.name,
                trace_id,
                response.metadata.get("agent"),
            )

    def on_error(self, env: IntentEnvelope, error: ErrorInfo) -> None:
        trace_id = getattr(env.metadata, "traceId", None)
        self._log.error(
            "Routing error for intent '%s' (traceId=%s, code=%s, message=%s)",
            env.intent.name,
            trace_id,
            error.code,
            error.message,
        )


class MetricsRouterMiddleware:
    """
    Metrics + trace middleware backed by Telemetry.

    Emits:
      - metrics.intent_request (via Telemetry.record_request)
      - optional span record (via Telemetry.record_span)

    This is transport-agnostic: works for HTTP, ZMQ, in-process, etc.
    """

    def __init__(self) -> None:
        self._telemetry = get_telemetry()

    def before_route(self, env: IntentEnvelope) -> None:
        # No-op for now; could start a live span if we integrate real OTEL here
        pass

    def after_route(self, env: IntentEnvelope, response: AgentResponse) -> None:
        trace_id = getattr(env.metadata, "traceId", None)
        agent = response.metadata.get("agent", "unknown")
        latency_ms = int(response.metadata.get("latencyMs", 0))  # router already logs spans; we can fuse later
        tenant = self._extract_tenant(env)
        subject = self._extract_subject(env)

        self._telemetry.record_request(
            intent=env.intent.name,
            agent=agent,
            success=(response.error is None),
            latency_ms=latency_ms,
            tenant=tenant,
            subject=subject,
            error_code=(response.error.code if response.error else None),
        )

        # Optional span logging
        # (we can later feed TraceSpan into Telemetry.record_span instead of duplicating)
        # from .telemetry import TelemetrySpan
        # self._telemetry.record_span(
        #     TelemetrySpan(
        #         trace_id=trace_id or "",
        #         intent=env.intent.name,
        #         agent=agent,
        #         latency_ms=latency_ms,
        #         success=(response.error is None),
        #         error_code=(response.error.code if response.error else None),
        #     )
        # )

    def on_error(self, env: IntentEnvelope, error: ErrorInfo) -> None:
        trace_id = getattr(env.metadata, "traceId", None)
        agent = "router"
        tenant = self._extract_tenant(env)
        subject = self._extract_subject(env)

        self._telemetry.record_request(
            intent=env.intent.name,
            agent=agent,
            success=False,
            latency_ms=0,
            tenant=tenant,
            subject=subject,
            error_code=error.code,
        )

    @staticmethod
    def _extract_tenant(env: IntentEnvelope) -> Optional[str]:
        caller = getattr(env.metadata, "caller", None)
        if isinstance(caller, dict):
            return caller.get("tenant")
        return None

    @staticmethod
    def _extract_subject(env: IntentEnvelope) -> Optional[str]:
        caller = getattr(env.metadata, "caller", None)
        if isinstance(caller, dict):
            return caller.get("sub")
        return None
