from __future__ import annotations

from typing import List, Dict, Any

from intentusnet.core.agent import BaseAgent
from intentusnet.protocol import AgentDefinition, Capability, IntentRef, AgentResponse


class WebSearchAgent(BaseAgent):
    """
    Mock web search agent for demo purposes.

    Input:
        { "topic": "..." }

    Output:
        {
            "results": [
                { "title": "...", "snippet": "...", "url": "..." },
                ...
            ]
        }
    """

    def __init__(self, router):
        definition = AgentDefinition(
            name="web-search-agent",
            capabilities=[
                Capability(intent=IntentRef("SearchIntent"))
            ],
        )
        super().__init__(definition, router)

    # ----------------------------------------------------------
    # Main handler
    # ----------------------------------------------------------
    def handle_intent(self, env) -> AgentResponse:
        topic = env.payload.get("topic", "").strip()

        if not topic:
            return AgentResponse.failure(
                self.error("Missing 'topic'"),
                agent=self.definition.name,
                trace_id=env.metadata.traceId,
            )

        # Simulated search results (replaceable later with real integration)
        results = self._mock_search(topic)

        return AgentResponse.success(
            {"results": results},
            agent=self.definition.name,
            trace_id=env.metadata.traceId,
        )

    # ----------------------------------------------------------
    # Fake search implementation
    # ----------------------------------------------------------
    def _mock_search(self, topic: str) -> List[Dict[str, Any]]:
        """
        Return 3 fake search results.
        These are deterministic and safe for demo purposes.
        """
        return [
            {
                "title": f"Overview of {topic}",
                "snippet": f"General background and key concepts related to {topic}.",
                "url": f"https://example.com/{topic}/overview",
            },
            {
                "title": f"Deep dive into {topic}",
                "snippet": f"Detailed exploration and analysis of {topic}.",
                "url": f"https://example.com/{topic}/deep-dive",
            },
            {
                "title": f"Applications of {topic}",
                "snippet": f"Real-world use cases and applications involving {topic}.",
                "url": f"https://example.com/{topic}/applications",
            },
        ]
