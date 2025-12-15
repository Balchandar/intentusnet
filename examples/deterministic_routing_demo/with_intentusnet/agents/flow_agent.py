from __future__ import annotations

from typing import Any

from intentusnet.core.agent import BaseAgent
from intentusnet.protocol.response import AgentResponse
from intentusnet.protocol import AgentDefinition, Capability, IntentRef, RoutingOptions
from intentusnet.protocol.enums import RoutingStrategy

class SearchAndSummarizeFlowAgent(BaseAgent):
    def __init__(self, router: Any):
        definition = AgentDefinition(
            name="flow-search-summarize",
            capabilities=[Capability(intent=IntentRef(name="SearchAndSummarizeIntent", version="1.0"))],
        )
        setattr(definition, "nodeId", None)
        setattr(definition, "nodePriority", 5)
        super().__init__(definition=definition, router=router)

    def handle_intent(self, env) -> AgentResponse:
        q = (env.payload.get("query") or "").strip()
        if not q:
            return AgentResponse.failure(self.error("missing query"),
                                        agent=self.definition.name,
                                        trace_id=env.metadata.traceId)

        # Router-owned fallback (local -> remote) by strategy
        search = self.emit_intent(
            "SearchIntent",
            {"query": q},
            routing=RoutingOptions(strategy=RoutingStrategy.FALLBACK),
        )
        if search.error:
            return search

        summary = self.emit_intent("SummarizeIntent", {"results": search.payload["results"]})
        if summary.error:
            return summary

        return AgentResponse.success(
            payload={
                "query": q,
                "summary": summary.payload["summary"],
                "results": search.payload["results"],
            },            
            agent=self.definition.name,
            trace_id=env.metadata.traceId
        )
