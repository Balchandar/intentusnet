from __future__ import annotations

import uuid
import datetime as dt

from intentusnet.core.runtime import IntentusRuntime
from intentusnet.protocol.intent import (
    IntentRef, IntentEnvelope,
    IntentContext, IntentMetadata,
    RoutingOptions, RoutingMetadata,
)
from intentusnet.protocol.response import AgentResponse
from intentusnet.protocol.validators import (
    validate_intent_envelope,
    validate_agent_response,
)

# import your agents same as HTTP demo
from .agents.nlu_agent import NLUAgent
from .agents.research_orchestrator import ResearchOrchestratorAgent
from .agents.web_search_agent import WebSearchAgent
from .agents.alt_search_agent import AltSearchAgent
from .agents.scraper_agent import ScraperAgent
from .agents.cleaner_agent import CleanerAgent
from .agents.summarizer_agent import SummarizerAgent
from .agents.reasoning_agent import ReasoningAgent
from .agents.action_agent import ActionAgent


# ----------------------------------------------------------------------
# Build runtime
# ----------------------------------------------------------------------
runtime = IntentusRuntime()
runtime.register_agent(lambda r: NLUAgent(r))
runtime.register_agent(lambda r: WebSearchAgent(r))
runtime.register_agent(lambda r: AltSearchAgent(r))
runtime.register_agent(lambda r: ScraperAgent(r))
runtime.register_agent(lambda r: CleanerAgent(r))
runtime.register_agent(lambda r: SummarizerAgent(r))
runtime.register_agent(lambda r: ReasoningAgent(r))
runtime.register_agent(lambda r: ActionAgent(r))
runtime.register_agent(lambda r: ResearchOrchestratorAgent(r))


# ----------------------------------------------------------------------
# MCP → Intent mapping
# ----------------------------------------------------------------------
def mcp_request_to_intent(tool_name: str, arguments: dict) -> IntentEnvelope:
    """
    Example mapping from MCP-style "tool call" into IntentEnvelope.
    """

    now = dt.datetime.now(dt.timezone.utc).isoformat() + "Z"

    payload = {
        "version": "1.0",
        "intent": {"name": tool_name, "version": "1.0"},
        "payload": arguments,
        "context": {
            "sourceAgent": "mcp-client",
            "timestamp": now,
            "priority": 1,
            "tags": [],
        },
        "metadata": {
            "requestId": str(uuid.uuid4()),
            "source": "mcp-client",
            "createdAt": now,
            "traceId": str(uuid.uuid4()),
        },
        "routing": {"targetAgent": None, "fallbackAgents": []},
        "routingMetadata": {"decisionPath": [], "retries": 0},
    }

    validate_intent_envelope(payload)

    return IntentEnvelope(
        version="1.0",
        intent=IntentRef(tool_name),
        payload=arguments,
        context=IntentContext(**payload["context"]),
        metadata=IntentMetadata(**payload["metadata"]),
        routing=RoutingOptions(),
        routingMetadata=RoutingMetadata(),
    )


# ----------------------------------------------------------------------
# Handle MCP request
# ----------------------------------------------------------------------
def handle_mcp_call(tool_name: str, args: dict) -> dict:
    env = mcp_request_to_intent(tool_name, args)

    result: AgentResponse = runtime.router.route_intent(env)

    result_dict = {
        "version": result.version,
        "status": result.status,
        "payload": result.payload,
        "metadata": result.metadata,
        "error": result.error.__dict__ if result.error else None,
    }

    validate_agent_response(result_dict)

    return result_dict
