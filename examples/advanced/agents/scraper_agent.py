from intentusnet.agents.base import BaseAgent
from intentusnet.protocol.models import AgentDefinition, Capability, AgentResponse, IntentRef


class ScraperAgent(BaseAgent):

    def __init__(self, router):
        definition = AgentDefinition(
            name="scraper-agent",
            capabilities=[
               Capability(intent=IntentRef("ExtractIntent"),inputSchema={},outputSchema={})
            ],
        )
        super().__init__(definition, router)

    def handle(self, env):
        response = env.payload.get("results", [])
        if not response:
            return AgentResponse.failure(self.error("No results to scrape"))
        combined = "\n".join((r["title"] for r in response["results"]) if "results" in response else [])
        return AgentResponse.success({"content": combined})
