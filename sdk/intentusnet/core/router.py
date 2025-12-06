from __future__ import annotations
from typing import Optional
import uuid
import datetime as dt
import logging

from ..protocol.models import (
    IntentEnvelope,
    AgentResponse,
    ErrorInfo,
    RouterDecision,
    TraceSpan,
)
from ..protocol.enums import ErrorCode, RoutingStrategy
from ..protocol.errors import IntentusError, RoutingError
from .tracing import TraceSink, InMemoryTraceSink
from .registry import AgentRegistry

logger = logging.getLogger("intentusnet.router")


class IntentRouter:
    """
    Core routing engine:
    - Select agent
    - Apply fallback (registry or envelope)
    - Execute agent
    - Capture trace spans
    - Normalize errors
    """

    def __init__(self, registry: AgentRegistry, trace_sink: Optional[TraceSink] = None) -> None:
        self._registry = registry
        self._trace_sink = trace_sink or InMemoryTraceSink()

    @staticmethod
    def _now_iso() -> str:
        return dt.datetime.utcnow().isoformat() + "Z"

    # -----------------------------------------------------------
    # Agent Selection
    # -----------------------------------------------------------

    def _select_agent(self, env: IntentEnvelope) -> RouterDecision:
        """
        Select the primary agent and compute effective fallback order.

        Fallback priority:
            1) Explicit override from env.routing.fallbackAgents
            2) Registry capability-level fallbackAgents
        """

        # Find agents that can handle this intent
        candidates = self._registry.find_agents_for_intent(env.intent)
        if not candidates:
            raise RoutingError(f"No agent found for intent={env.intent.name} v={env.intent.version}")

        # TargetAgent override from envelope
        if env.routing.targetAgent:
            agent_name = env.routing.targetAgent
            matched = self._registry.get_agent(agent_name)
            if matched is None:
                raise RoutingError(f"Target agent '{agent_name}' is not registered")
            selected_agent = matched
        else:
            # Default: pick the first matching capability
            selected_agent = candidates[0]

        selected_name = selected_agent.definition.name

        # -------------------------------------------------------
        # Determine fallback chain from registry capability
        # -------------------------------------------------------

        registry_fallback: list[str] = []

        for cap in selected_agent.definition.capabilities:
            # Capability.intent is an IntentRef - match correctly
            if (
                cap.intent.name == env.intent.name
                and cap.intent.version == env.intent.version
            ):
                registry_fallback = list(cap.fallbackAgents) if cap.fallbackAgents else []
                break

        # -------------------------------------------------------
        # Effective fallback: envelope override > registry default
        # -------------------------------------------------------
        if env.routing.fallbackAgents:
            effective_fallback = list(env.routing.fallbackAgents)
        else:
            effective_fallback = registry_fallback

        return RouterDecision(
            selectedAgent=selected_name,
            routingStrategy=RoutingStrategy.DIRECT,
            fallbackOrder=effective_fallback,
            reason="First matching capability with registry-based fallback support",
            traceId=env.metadata.traceId,
        )

    # -----------------------------------------------------------
    # Routing Loop with Fallback
    # -----------------------------------------------------------

    def route_intent(self, env: IntentEnvelope) -> AgentResponse:
        start = dt.datetime.utcnow()
        decision: Optional[RouterDecision] = None
        attempt = 0
        last_error: Optional[ErrorInfo] = None
        active_agent_name: str = "router"

        while True:
            attempt += 1

            try:
                if decision is None:
                    decision = self._select_agent(env)

                agent = self._registry.get_agent(decision.selectedAgent)
                if not agent:
                    raise RoutingError(f"Agent '{decision.selectedAgent}' is not registered")

                active_agent_name = agent.definition.name
                env.routingMetadata.previousAgents.append(active_agent_name)

                logger.info(
                    "Routing intent '%s' → agent '%s' (attempt=%d, fallbackRemaining=%s)",
                    env.intent.name,
                    active_agent_name,
                    attempt,
                    decision.fallbackOrder,
                )

                # Execute the agent
                resp = agent.handle_intent(env)

                # ---- Tracing ----
                end = dt.datetime.utcnow()
                latency_ms = int((end - start).total_seconds() * 1000)

                span = TraceSpan(
                    traceId=env.metadata.traceId,
                    spanId=str(uuid.uuid4()),
                    parentSpanId=None,
                    agent=active_agent_name,
                    intent=env.intent.name,
                    startTime=start.isoformat() + "Z",
                    endTime=end.isoformat() + "Z",
                    latencyMs=latency_ms,
                    status=resp.status,
                    error=resp.error,
                )
                self._trace_sink.record(span)

                return resp

            except IntentusError as ex:
                # Structured internal agent error
                logger.error("Intentus error during routing: %s", ex)
                last_error = ErrorInfo(
                    code=ErrorCode.INTERNAL_AGENT_ERROR,
                    message=str(ex),
                    retryable=False,
                    details={},
                )

            except Exception as ex:
                # Unhandled unexpected error
                logger.exception("Unexpected error during agent execution")
                last_error = ErrorInfo(
                    code=ErrorCode.INTERNAL_AGENT_ERROR,
                    message=str(ex),
                    retryable=False,
                    details={},
                )

            # -------------------------------------------------------
            # Fallback Logic
            # -------------------------------------------------------
            if decision and decision.fallbackOrder:
                next_agent = decision.fallbackOrder.pop(0)

                logger.warning(
                    "Fallback activated: %s → %s (remaining=%s)",
                    decision.selectedAgent,
                    next_agent,
                    decision.fallbackOrder,
                )

                decision.selectedAgent = next_agent
                decision.routingStrategy = RoutingStrategy.FALLBACK
                continue

            # No fallback options left; break and return error
            break

        # -----------------------------------------------------------
        # Final Failure
        # -----------------------------------------------------------
        return AgentResponse(
            version=env.version,
            status="error",
            payload=None,
            metadata={
                "agent": active_agent_name,
                "timestamp": self._now_iso(),
                "traceId": env.metadata.traceId,
            },
            error=last_error
            or ErrorInfo(
                code=ErrorCode.ROUTING_ERROR,
                message="Failed to route intent",
                retryable=False,
                details={},
            ),
        )
