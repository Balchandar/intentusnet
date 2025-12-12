from __future__ import annotations

from typing import List, Dict, Any

from intentusnet.core.agent import BaseAgent
from intentusnet.protocol import AgentDefinition, Capability, IntentRef, AgentResponse


class ScraperAgent(BaseAgent):
    """
    Convert search result metadata into extracted "raw content".

    Input:
        { "results": [ {title, snippet, url}, ... ] }

    Output:
        { "content": "<combined text>" }
    """

    def __init__(self, router):
        definition = AgentDefinition(
            name="scraper-agent",
            capabilities=[
                Capability(intent=IntentRef("ExtractIntent"))
            ],
        )
        super().__init__(definition, router)

    # ----------------------------------------------------------
    # Main Handler
    # ----------------------------------------------------------
    def handle_intent(self, env) -> AgentResponse:
        results = env.payload.get("results", None)

        if not isinstance(results, list):
            return AgentResponse.failure(
                self.error("Missing or invalid 'results' list"),
                agent=self.definition.name,
                trace_id=env.metadata.traceId,
            )

        if not results:
            return AgentResponse.failure(
                self.error("Empty search results — nothing to extract"),
                agent=self.definition.name,
                trace_id=env.metadata.traceId,
            )

        raw_content = self._extract(results)

        return AgentResponse.success(
            {"content": raw_content},
            agent=self.definition.name,
            trace_id=env.metadata.traceId,
        )

    # ----------------------------------------------------------
    # Content Extraction Logic
    # ----------------------------------------------------------
    def _extract(self, results: List[Dict[str, Any]]) -> str:
        """
        Create a combined text block using titles & snippets.
        This acts like a simplified "scraper".
        """
        blocks = []

        for r in results:
            title = r.get("title", "").strip()
            snippet = r.get("snippet", "").strip()

            if title:
                blocks.append(f"# {title}")

            if snippet:
                blocks.append(snippet)

        return "\n\n".join(blocks)
