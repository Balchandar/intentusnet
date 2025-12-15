from __future__ import annotations

from typing import Any, Dict

from intentusnet.core.agent import BaseAgent
from intentusnet.protocol import AgentDefinition, Capability, IntentRef, AgentResponse


class ResearchOrchestratorAgent(BaseAgent):
    """
    Multi-step orchestrator for research tasks.

    Pipeline:
        1. SearchIntent(topic)
        2. ExtractIntent(results)
        3. CleanIntent(content)
        4. SummarizeIntent(cleanedContent)

    Output:
        { "summary": "..." }
    """

    def __init__(self, router):
        definition = AgentDefinition(
            name="research-orchestrator",
            capabilities=[
                Capability(intent=IntentRef("ResearchIntent"))
            ],
        )
        super().__init__(definition, router)

    # ----------------------------------------------------------
    # Main Handler
    # ----------------------------------------------------------
    def handle_intent(self, env) -> AgentResponse:
        topic = env.payload.get("topic", "").strip()

        if not topic:
            return AgentResponse.failure(
                self.error("Missing 'topic' field"),
                agent=self.definition.name,
                trace_id=env.metadata.traceId,
            )

        # Step 1 — Search
        search = self.emit_intent("SearchIntent", {"topic": topic})
        if search.status == "error":
            return search

        results = search.payload.get("results", [])

        # Step 2 — Extract content from search results
        extract = self.emit_intent("ExtractIntent", {"results": results})
        if extract.status == "error":
            return extract

        content = extract.payload.get("content", "")

        # Step 3 — Clean the content
        cleaned = self.emit_intent("CleanIntent", {"content": content})
        if cleaned.status == "error":
            return cleaned

        cleaned_text = cleaned.payload.get("cleaned", "")

        # Step 4 — Summarize
        summary = self.emit_intent("SummarizeIntent", {"text": cleaned_text})
        if summary.status == "error":
            return summary

        final_summary = summary.payload.get("summary", "")

        # Return final combined output
        return AgentResponse.success(
            {"summary": final_summary, "topic": topic},
            agent=self.definition.name,
            trace_id=env.metadata.traceId,
        )
