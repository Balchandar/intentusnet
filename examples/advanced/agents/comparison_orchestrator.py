from intentusnet.agents.base import BaseAgent
from intentusnet.protocol.models import AgentDefinition, Capability, AgentResponse


class ComparisonOrchestratorAgent(BaseAgent):

    def __init__(self, router):
        definition = AgentDefinition(
            name="comparison-orchestrator",
            capabilities=[
                Capability(
                    name="comparison",
                    intents=["CompareIntent"],
                    priority=1,
                )
            ],
        )
        super().__init__(definition, router)

    def handle(self, env):
        topics = env.payload.get("topics", [])
        if not topics or len(topics) != 2:
            return AgentResponse.failure(self.error("Comparison: expected two topics"))

        A, B = topics

        # Run ResearchIntent twice
        resA = self.emit_intent("ResearchIntent", {"topic": A})
        if resA.error:
            return resA

        resB = self.emit_intent("ResearchIntent", {"topic": B})
        if resB.error:
            return resB

        # Simple comparison logic
        return AgentResponse.success({
            "compare": {
                "topicA": resA.payload,
                "topicB": resB.payload,
            },
            "insight": f"Compared {A} vs {B}"
        })
