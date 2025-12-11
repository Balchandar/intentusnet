# FILE: src/intentusnet/core/router.py

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
)
from ..protocol.enums import ErrorCode, RoutingStrategy
from ..protocol.errors import IntentusError, RoutingError
from .tracing import TraceSink, InMemoryTraceSink, TraceSpan
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

    # -------------------------------------------------------
    # Utilities
    # -------------------------------------------------------

    @staticmethod
    def _now_iso() -> str:
        return dt.datetime.now(dt.timezone.utc).isoformat()

    def _build_decision(self, env: IntentEnvelope) -> RouterDecision:
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
                registry_fallback = cap.fallbackAgents or []
                break

        # Envelope-level fallback overrides registry
        envelope_fallback = env.routing.fallbackAgents or []

        effective_fallback: list[str] = envelope_fallback or registry_fallback

        return RouterDecision(
            selectedAgent=selected_name,
            routingStrategy=RoutingStrategy.DIRECT,
            fallbackOrder=effective_fallback,
            reason="env.targetAgent or first-capability",
            traceId=env.metadata.traceId,
        )

    # -------------------------------------------------------
    # Main routing entrypoint
    # -------------------------------------------------------

    def route_intent(self, env: IntentEnvelope) -> AgentResponse:
        """
        Route an intent envelope to the appropriate agent with fallback handling.
        """
        decision = self._build_decision(env)

        # Used in final error response if everything fails
        active_agent_name: Optional[str] = None
        last_error: Optional[ErrorInfo] = None

        # Prepare a working list of agents to try:
        # primary first, then fallback chain
        remaining_agents: list[str] = [decision.selectedAgent] + list(decision.fallbackOrder)

        attempt = 0

        while remaining_agents:
            attempt += 1
            active_agent_name = remaining_agents.pop(0)

            agent = self._registry.get_agent(active_agent_name)
            if agent is None:
                # Skip unknown agent; move to next fallback
                logger.warning("Agent '%s' not registered, skipping.", active_agent_name)
                continue

            start = dt.datetime.now(dt.timezone.utc)

            try:
                # Update routing metadata
                env.routingMetadata.previousAgents.append(active_agent_name)

                logger.info(
                    "Routing intent '%s' → agent '%s' (attempt=%d, fallbackRemaining=%s)",
                    env.intent.name,
                    active_agent_name,
                    attempt,
                    decision.fallbackOrder,
                )

                # Execute the agent
                resp = agent.handle(env)

                # ---- Tracing Block (UPDATED FOR NEW TraceSpan MODEL) ----
                end = dt.datetime.now(dt.timezone.utc)
                latency_ms = int((end - start).total_seconds() * 1000)
             
                span_dict = {
                    "id": str(uuid.uuid4()),
                    "name": f"{active_agent_name}:{env.intent.name}",
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z",
                    "attributes": {
                        "agent": active_agent_name,
                        "intent": env.intent.name,
                        "latencyMs": latency_ms,
                        "status": resp.status,
                        "error": resp.error.message if resp.error else "",
                    },
                }

                self._trace_sink.record(
                    traceId=env.metadata.traceId,
                    span=span_dict
                )


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

            # -----------------------------------------------------------
            # Fall back to the next agent, if any
            # -----------------------------------------------------------
            if remaining_agents:
                next_agent = remaining_agents[0]

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
