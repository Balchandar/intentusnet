from intentusnet.agents.base import BaseAgent
from intentusnet.protocol.models import AgentDefinition, Capability, AgentResponse, IntentRef


class ReasoningAgent(BaseAgent):

    def __init__(self, router):
        definition = AgentDefinition(
            name="reasoning-agent",
            capabilities=[
                    Capability(
                    intent=IntentRef("ReasoningIntent"),
                    inputSchema={},
                    outputSchema={}
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
