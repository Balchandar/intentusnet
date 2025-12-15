from __future__ import annotations

from typing import List, Dict, Any

from intentusnet.core.agent import BaseAgent
from intentusnet.protocol import AgentDefinition, Capability, IntentRef, AgentResponse


class AltSearchAgent(BaseAgent):
    """
    Secondary / fallback search agent.

    Used when WebSearchAgent fails, or if
    fallbackAgents is explicitly set in RoutingOptions.
    """

    def __init__(self, router):
        definition = AgentDefinition(
            name="alt-search-agent",
            capabilities=[
                Capability(intent=IntentRef("SearchIntent"))
            ],
        )
        super().__init__(definition, router)

    # ----------------------------------------------------------
    # Handle SearchIntent
    # ----------------------------------------------------------
    def handle_intent(self, env) -> AgentResponse:
        topic = env.payload.get("topic", "").strip()

        if not topic:
            return AgentResponse.failure(
                self.error("Missing 'topic' for fallback search"),
                agent=self.definition.name,
                trace_id=env.metadata.traceId,
            )

        # Fallback deterministic results
        results = self._fallback_results(topic)

        return AgentResponse.success(
            {"results": results},
            agent=self.definition.name,
            trace_id=env.metadata.traceId,
        )

    # ----------------------------------------------------------
    # Fallback search logic
    # ----------------------------------------------------------
    def _fallback_results(self, topic: str) -> List[Dict[str, Any]]:
        """
        Return basic alternative search results.
        This ensures the orchestrator has usable downstream data
        even if the main search agent fails.
        """
        return [
            {
                "title": f"Alternative introduction to {topic}",
                "snippet": f"Basic high-level information about {topic}.",
                "url": f"https://alt.example.com/{topic}/intro",
            },
            {
                "title": f"{topic}: Key facts",
                "snippet": f"Important facts and notes related to {topic}.",
                "url": f"https://alt.example.com/{topic}/facts",
            },
        ]
