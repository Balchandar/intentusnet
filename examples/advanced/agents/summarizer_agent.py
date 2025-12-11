from intentusnet.agents.base import BaseAgent
from intentusnet.protocol.models import AgentDefinition, Capability, AgentResponse, IntentRef


class SummarizerAgent(BaseAgent):

    def __init__(self, router):
        definition = AgentDefinition(
            name="summarizer-agent",
            capabilities=[
               Capability(
                    intent=IntentRef("SummarizeIntent"),
                    inputSchema={},
                    outputSchema={}
                )

            ],
        )
        super().__init__(definition, router)

    def handle(self, env):
        content = env.payload.get("content", "")
        summary = content[:120] + "..." if len(content) > 120 else content
        return AgentResponse.success({"summary": summary})
