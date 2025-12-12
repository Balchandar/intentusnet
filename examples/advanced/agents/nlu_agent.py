from __future__ import annotations

from typing import Dict, Any

from intentusnet.core.agent import BaseAgent
from intentusnet.protocol import AgentDefinition, Capability, IntentRef, AgentResponse


class NLUAgent(BaseAgent):
    """
    Very simple NLU classifier used by the research demo.

    Input:
        { "text": "..." }

    Output:
        {
            "intent": <IntentName>,
            "arguments": {...}
        }
    """

    def __init__(self, router):
        definition = AgentDefinition(
            name="nlu-agent",
            capabilities=[
                Capability(intent=IntentRef("ParseIntent"))
            ],
        )
        super().__init__(definition, router)

    def handle_intent(self, env) -> AgentResponse:
        text: str = env.payload.get("text", "").strip()

        if not text:
            return AgentResponse.failure(
                self.error("No input text provided"),
                agent=self.definition.name,
                trace_id=env.metadata.traceId,
            )

        # Very naive intent classification — demo only
        lower = text.lower()

        if "compare" in lower or "vs" in lower:
            # e.g., "compare python vs javascript"
            return AgentResponse.success(
                {
                    "intent": "CompareIntent",
                    "arguments": self._parse_compare(text),
                },
                agent=self.definition.name,
                trace_id=env.metadata.traceId,
            )

        # Default: treat as research request
        return AgentResponse.success(
            {
                "intent": "ResearchIntent",
                "arguments": {"topic": text},
            },
            agent=self.definition.name,
            trace_id=env.metadata.traceId,
        )

    # ----------------------------------------------------------
    # Internal parsing helpers
    # ----------------------------------------------------------

    def _parse_compare(self, text: str) -> Dict[str, Any]:
        """
        Extract entities around "compare" or "vs".
        Very naive but fine for demo.
        """
        lower = text.lower()

        if " vs " in lower:
            a, b = text.split(" vs ", 1)
            return {"a": a.strip(), "b": b.strip()}

        if "compare" in lower:
            phrase = text.lower().replace("compare", "").strip()
            parts = phrase.split()
            if len(parts) >= 2:
                return {"a": parts[0], "b": parts[1]}

        # fallback
        return {"a": text, "b": text}
