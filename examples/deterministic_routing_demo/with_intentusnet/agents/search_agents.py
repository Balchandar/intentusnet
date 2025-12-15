from __future__ import annotations

from typing import Any

from intentusnet.core.agent import BaseAgent
from intentusnet.protocol.response import AgentResponse
from intentusnet.protocol import AgentDefinition, Capability, IntentRef

class LocalSearchAgent(BaseAgent):
    def __init__(self, router: Any):
        definition = AgentDefinition(
            name="search-local",
            capabilities=[Capability(intent=IntentRef(name="SearchIntent", version="1.0"))],
        )
        setattr(definition, "nodeId", None)
        setattr(definition, "nodePriority", 10)
        super().__init__(definition=definition, router=router)
        self._fail_once = True

    def handle_intent(self, env) -> AgentResponse:
        q = (env.payload.get("query") or "").strip()
        if not q:
            return AgentResponse.failure(self.error("missing query"),
                                        agent=self.definition.name,
                                        trace_id=env.metadata.traceId)
        if self._fail_once:
            self._fail_once = False
            return AgentResponse.failure(self.error("local search warming up (simulated failure)"),
                                        agent=self.definition.name,
                                        trace_id=env.metadata.traceId)
        return AgentResponse.success(payload={"results": [f"local:{q}:a", f"local:{q}:b"]},
                                    agent=self.definition.name,
                                    trace_id=env.metadata.traceId)

class RemoteSearchAgent(BaseAgent):
    def __init__(self, router: Any):
        definition = AgentDefinition(
            name="search-remote",
            capabilities=[Capability(intent=IntentRef(name="SearchIntent", version="1.0"))],
        )
        setattr(definition, "nodeId", "node-b")
        setattr(definition, "nodePriority", 50)
        super().__init__(definition=definition, router=router)

    def handle_intent(self, env) -> AgentResponse:
        q = (env.payload.get("query") or "").strip()
        if not q:
            return AgentResponse.failure(self.error("missing query"),
                                        agent=self.definition.name,
                                        trace_id=env.metadata.traceId)
        return AgentResponse.success(payload={"results": [f"remote:{q}:1", f"remote:{q}:2", f"remote:{q}:3"]},
                                    agent=self.definition.name,
                                    trace_id=env.metadata.traceId)

class SummarizeAgent(BaseAgent):
    def __init__(self, router: Any):
        definition = AgentDefinition(
            name="summarize",
            capabilities=[Capability(intent=IntentRef(name="SummarizeIntent", version="1.0"))],
        )
        setattr(definition, "nodeId", None)
        setattr(definition, "nodePriority", 10)
        super().__init__(definition=definition, router=router)

    def handle_intent(self, env) -> AgentResponse:
        results = env.payload.get("results") or []
        if not results:
            return AgentResponse.failure(self.error("no results"),
                                        agent=self.definition.name,
                                        trace_id=env.metadata.traceId)
        return AgentResponse.success(payload={"summary": f"summary(len={len(results)})"},
                                    agent=self.definition.name,
                                    trace_id=env.metadata.traceId)
