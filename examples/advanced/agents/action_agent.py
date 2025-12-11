from intentusnet.agents.base import BaseAgent
from intentusnet.protocol.models import AgentDefinition, Capability, AgentResponse, IntentRef


class ActionAgent(BaseAgent):

    def __init__(self, router):
        definition = AgentDefinition(
            name="action-agent",
            capabilities=[
                Capability(
                    intent=IntentRef("ActionIntent"),
                    inputSchema={},
                    outputSchema={}
                )
            ],
        )
        super().__init__(definition, router)

    def handle(self, env):
        reasoning = env.payload.get("reasoning", "")
        recommendation = f"Recommended: explore more about this because {reasoning}."
        return AgentResponse.success({
            "final_action": recommendation
        })
