from __future__ import annotations

from typing import Any

from intentusnet.core.agent import BaseAgent
from intentusnet.protocol.response import AgentResponse
from intentusnet.protocol import AgentDefinition, Capability, IntentRef

from .mock_mcp_server import call_tool

class MCPBackedSearchAgent(BaseAgent):
    def __init__(self, router: Any):
        definition = AgentDefinition(
            name="search-mcp-remote",
            capabilities=[Capability(intent=IntentRef(name="SearchIntent", version="1.0"))],
        )
        setattr(definition, "nodeId", "mcp-node")
        setattr(definition, "nodePriority", 50)
        super().__init__(definition=definition, router=router)

    def handle_intent(self, env) -> AgentResponse:
        try:
            result = call_tool(env.intent.name, env.payload)
            return AgentResponse.success(payload=result,                                         
                                        agent=self.definition.name,
                                        trace_id=env.metadata.traceId)
        except Exception as ex:
            return AgentResponse.failure(self.error(f"mcp tool call failed: {ex}"),
                                        agent=self.definition.name,
                                        trace_id=env.metadata.traceId)
