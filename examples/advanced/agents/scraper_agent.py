from intentusnet.agents.base import BaseAgent
from intentusnet.protocol.models import AgentDefinition, Capability, AgentResponse


class ScraperAgent(BaseAgent):

    def __init__(self, router):
        definition = AgentDefinition(
            name="scraper-agent",
            capabilities=[
                Capability(
                    name="scraper",
                    intents=["ExtractIntent"],
                    priority=1,
                )
            ],
        )
        super().__init__(definition, router)

    def handle(self, env):
        results = env.payload.get("results", [])
        if not results:
            return AgentResponse.failure(self.error("No results to scrape"))

        combined = "\n".join(r["title"] for r in results)
        return AgentResponse.success({"content": combined})
