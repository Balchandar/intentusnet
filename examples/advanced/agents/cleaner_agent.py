from intentusnet.agents.base import BaseAgent
from intentusnet.protocol.models import AgentDefinition, Capability, AgentResponse


class CleanerAgent(BaseAgent):

    def __init__(self, router):
        definition = AgentDefinition(
            name="cleaner-agent",
            capabilities=[
                Capability(
                    name="cleaner",
                    intents=["CleanIntent"],
                    priority=1,
                )
            ],
        )
        super().__init__(definition, router)

    def handle(self, env):
        content = env.payload.get("content", "")
        cleaned = content.replace("\n", " ").strip().lower()
        return AgentResponse.success({"clean": cleaned})
