from intentusnet.agents.base import BaseAgent
from intentusnet.protocol.models import AgentDefinition, Capability, AgentResponse


class ActionAgent(BaseAgent):

    def __init__(self, router):
        definition = AgentDefinition(
            name="action-agent",
            capabilities=[
                Capability(
                    name="action",
                    intents=["ActionIntent"],
                    priority=1,
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
