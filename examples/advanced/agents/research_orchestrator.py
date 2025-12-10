from intentusnet.agents.base import BaseAgent
from intentusnet.protocol.models import AgentDefinition, Capability, AgentResponse


class ResearchOrchestratorAgent(BaseAgent):

    def __init__(self, router):
        definition = AgentDefinition(
            name="research-orchestrator",
            capabilities=[
                Capability(
                    name="research-orchestrator",
                    intents=["ResearchIntent"],
                    priority=1,
                )
            ],
        )
        super().__init__(definition, router)

    def handle(self, env):
        topic = env.payload.get("topic", "").strip()
        if not topic:
            return AgentResponse.failure(self.error("ResearchOrchestrator: missing topic"))

        # 1. Search
        search = self.emit_intent("SearchIntent", {"topic": topic})
        if search.error:
            return search

        # 2. Scrape
        extract = self.emit_intent("ExtractIntent", {"results": search.payload})
        if extract.error:
            return extract

        # 3. Clean
        cleaned = self.emit_intent("CleanIntent", {"content": extract.payload["content"]})
        if cleaned.error:
            return cleaned

        # 4. Summarize
        summary = self.emit_intent("SummarizeIntent", {"content": cleaned.payload["clean"]})
        if summary.error:
            return summary

        # 5. Reason
        reasoning = self.emit_intent("ReasonIntent", {"summary": summary.payload["summary"]})
        if reasoning.error:
            return reasoning

        # 6. Action
        action = self.emit_intent("ActionIntent", {"reasoning": reasoning.payload})
        return action
