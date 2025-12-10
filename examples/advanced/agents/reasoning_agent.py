from intentusnet.agents.base import BaseAgent
from intentusnet.protocol.models import AgentDefinition, Capability, AgentResponse


class ReasoningAgent(BaseAgent):

    def __init__(self, router):
        definition = AgentDefinition(
            name="reasoning-agent",
            capabilities=[
                Capability(
                    name="reasoning",
                    intents=["ReasonIntent"],
                    priority=1,
                )
            ],
        )
        super().__init__(definition, router)

    def handle(self, env):
        summary = env.payload.get("summary", "")
        reasoning = f"Based on the summary, the topic importance is {len(summary)} units."
        return AgentResponse.success({
            "reasoning": reasoning,
            "summary": summary,
        })
