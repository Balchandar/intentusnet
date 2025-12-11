from intentusnet.agents.base import BaseAgent
from intentusnet.protocol.models import AgentDefinition, Capability, IntentRef, AgentResponse


class WebSearchAgent(BaseAgent):

    def __init__(self, router):
        definition = AgentDefinition(
            name="web-search-agent",
            capabilities=[
                Capability(
                    intent=IntentRef(name="SearchIntent"),
                    inputSchema={},
                    outputSchema={}
                )
            ],
        )
        super().__init__(definition, router)

    def handle(self, env):
        topic = env.payload.get("topic", "")
        if "fail" in topic.lower():
            return AgentResponse.failure(self.error("Simulated search failure"))

        return AgentResponse.success({
            "results": [
                {"url": "http://example.com/1", "title": f"{topic} basic guide"},
                {"url": "http://example.com/2", "title": f"Advanced {topic}"},
            ]
        })
