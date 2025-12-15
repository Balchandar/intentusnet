from __future__ import annotations

import logging
import time
from typing import Protocol, runtime_checkable, Optional, Any

from ..protocol.intent import IntentEnvelope
from ..protocol.response import AgentResponse, ErrorInfo
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

    NOTE (v1):
    - We compute latency here using perf_counter because AgentResponse.metadata
      does not reliably contain latencyMs (router logs spans separately).
    """

    _START_KEY = "_intentusnet_start_perf"  # internal marker key

    def __init__(self) -> None:
        self._telemetry = get_telemetry()

    def before_route(self, env: IntentEnvelope) -> None:
        # Store start time on env.metadata (safe; it's already a dataclass in your model)
        setattr(env.metadata, self._START_KEY, time.perf_counter())

    def after_route(self, env: IntentEnvelope, response: AgentResponse) -> None:
        trace_id = getattr(env.metadata, "traceId", None)
        agent = response.metadata.get("agent", "unknown")

        start = getattr(env.metadata, self._START_KEY, None)
        latency_ms = int((time.perf_counter() - start) * 1000) if isinstance(start, (int, float)) else 0

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

        # Optional: attach latency for downstream callers (useful in demos)
        response.metadata.setdefault("latencyMs", latency_ms)
        if trace_id:
            response.metadata.setdefault("traceId", trace_id)

    def on_error(self, env: IntentEnvelope, error: ErrorInfo) -> None:
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
        caller: Any = getattr(env.metadata, "caller", None)
        if isinstance(caller, dict):
            return caller.get("tenant")
        return None

    @staticmethod
    def _extract_subject(env: IntentEnvelope) -> Optional[str]:
        caller: Any = getattr(env.metadata, "caller", None)
        if isinstance(caller, dict):
            return caller.get("sub")
        return None
