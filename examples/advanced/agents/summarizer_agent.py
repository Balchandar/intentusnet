from intentusnet.agents.base import BaseAgent
from intentusnet.protocol.models import AgentDefinition, Capability, AgentResponse


class SummarizerAgent(BaseAgent):

    def __init__(self, router):
        definition = AgentDefinition(
            name="summarizer-agent",
            capabilities=[
                Capability(
                    name="summarizer",
                    intents=["SummarizeIntent"],
                    priority=1,
                )
            ],
        )
        super().__init__(definition, router)

    def handle(self, env):
        content = env.payload.get("content", "")
        summary = content[:120] + "..." if len(content) > 120 else content
        return AgentResponse.success({"summary": summary})
