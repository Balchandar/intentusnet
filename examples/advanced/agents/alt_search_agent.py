from intentusnet.agents.base import BaseAgent
from intentusnet.protocol.models import AgentDefinition, Capability, AgentResponse


class AltSearchAgent(BaseAgent):

    def __init__(self, router):
        definition = AgentDefinition(
            name="alt-search-agent",
            capabilities=[
                Capability(
                    name="alt-search",
                    intents=["SearchIntent"],
                    priority=50,  # fallback (higher number = lower priority)
                )
            ],
        )
        super().__init__(definition, router)

    def handle(self, env):
        topic = env.payload.get("topic", "")
        return AgentResponse.success({
            "results": [
                {"url": "http://alt.com/a", "title": f"Alternative source for {topic}"},
            ]
        })
