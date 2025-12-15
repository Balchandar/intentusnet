from __future__ import annotations

import re
from typing import Any, Dict

from intentusnet.core.agent import BaseAgent
from intentusnet.protocol import AgentDefinition, Capability, IntentRef, AgentResponse


class CleanerAgent(BaseAgent):
    """
    Clean and normalize raw extracted content before summarization.

    Input:
        { "content": "raw text..." }

    Output:
        { "cleaned": "normalized text..." }
    """

    def __init__(self, router):
        definition = AgentDefinition(
            name="cleaner-agent",
            capabilities=[
                Capability(intent=IntentRef("CleanIntent"))
            ],
        )
        super().__init__(definition, router)

    # ----------------------------------------------------------
    # Main handler
    # ----------------------------------------------------------
    def handle_intent(self, env) -> AgentResponse:
        content = env.payload.get("content", "")

        if not isinstance(content, str) or not content.strip():
            return AgentResponse.failure(
                self.error("Missing or empty 'content'"),
                agent=self.definition.name,
                trace_id=env.metadata.traceId,
            )

        cleaned = self._clean_text(content)

        return AgentResponse.success(
            {"cleaned": cleaned},
            agent=self.definition.name,
            trace_id=env.metadata.traceId,
        )

    # ----------------------------------------------------------
    # Cleaning logic
    # ----------------------------------------------------------
    def _clean_text(self, text: str) -> str:
        """
        Deterministic cleaning steps:
        - Lowercase
        - Remove excess whitespace
        - Normalize punctuation
        - Remove repeated separators
        """
        t = text.lower()

        # Normalize punctuation spacing
        t = re.sub(r"\s+", " ", t)

        # Remove stray characters (demo-safe)
        t = re.sub(r"[^a-z0-9,.!?;:\s#\-]", "", t)

        # Remove duplicate punctuation
        t = re.sub(r"([,.!?;:])\1+", r"\1", t)

        # Trim
        t = t.strip()

        return t
