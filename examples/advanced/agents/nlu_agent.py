from intentusnet.agents.base import BaseAgent
from intentusnet.protocol.models import AgentDefinition, Capability, IntentRef, AgentResponse, ErrorInfo, ErrorCode


class NLUAgent(BaseAgent):

    def __init__(self, router):
        definition = AgentDefinition(
            name="nlu-agent",
            capabilities=[
                Capability(
                    intent=IntentRef(name="ParseIntent"),
                    inputSchema={"type": "object"},
                    outputSchema={"type": "object"},
                    fallbackAgents=[],
                    priority=0)

            ],
        )
        super().__init__(definition, router)

    def handle(self, env):
        q = env.payload.get("topic") or env.payload.get("query") or ""
        q = q.strip()

        if not q:
            return AgentResponse.failure(self.error("NLU: missing topic/query"))

        lower = q.lower()

        # Compare detection
        if " vs " in lower or "compare" in lower:
            cleaned = lower.replace("compare", "")
            parts = [p.strip() for p in cleaned.split("vs") if p.strip()]
            if len(parts) == 2:
                return AgentResponse.success({
                    "intent": "CompareIntent",
                    "topics": parts
                })

        # Deep research detection
        if "deep" in lower or "dive" in lower:
            return AgentResponse.success({
                "intent": "DeepResearchIntent",
                "topic": q
            })

        # Default → standard research
        return AgentResponse.success({
            "intent": "ResearchIntent",
            "topic": q
        })
