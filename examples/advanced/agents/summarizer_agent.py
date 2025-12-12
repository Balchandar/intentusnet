from __future__ import annotations

from typing import Any, Dict, List

from intentusnet.core.agent import BaseAgent
from intentusnet.protocol import AgentDefinition, Capability, IntentRef, AgentResponse


class SummarizerAgent(BaseAgent):
    """
    Deterministic mock summarizer used for the research pipeline.

    Input:
        { "text": "<cleaned text>" }

    Output:
        { "summary": "<short summary>" }
    """

    def __init__(self, router):
        definition = AgentDefinition(
            name="summarizer-agent",
            capabilities=[
                Capability(intent=IntentRef("SummarizeIntent"))
            ],
        )
        super().__init__(definition, router)

    # ----------------------------------------------------------
    # Main handler
    # ----------------------------------------------------------
    def handle_intent(self, env) -> AgentResponse:
        cleaned_text = env.payload.get("text", "")

        if not isinstance(cleaned_text, str) or not cleaned_text.strip():
            return AgentResponse.failure(
                self.error("Missing or empty 'text' for summarization"),
                agent=self.definition.name,
                trace_id=env.metadata.traceId,
            )

        summary = self._summarize(cleaned_text)

        return AgentResponse.success(
            {"summary": summary},
            agent=self.definition.name,
            trace_id=env.metadata.traceId,
        )

    # ----------------------------------------------------------
    # Deterministic summarizer (mock)
    # ----------------------------------------------------------
    def _summarize(self, text: str) -> str:
        """
        Simplified summarization algorithm (offline-safe):

        - Split into sentences
        - Select first 1–2 meaningful ones
        - Return compact result

        This ensures predictable demo output without LLM calls.
        """

        # Very simple sentence split
        sentences = [s.strip() for s in text.split(".") if s.strip()]

        if not sentences:
            return text[:200]  # fallback crop

        # Choose up to 2 important sentences
        selected = sentences[:2]

        return ". ".join(selected) + "."
