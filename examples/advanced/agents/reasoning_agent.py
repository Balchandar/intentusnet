from __future__ import annotations

from typing import Any, Dict

from intentusnet.core.agent import BaseAgent
from intentusnet.protocol import AgentDefinition, Capability, IntentRef, AgentResponse


class ReasoningAgent(BaseAgent):
    """
    Deterministic reasoning agent.

    Input:
        { "summary": "..." }

    Output:
        {
            "reasoning": "...derived or inferred insights..."
        }

    This is NOT an LLM — it simulates rule-based or heuristic reasoning.
    """

    def __init__(self, router):
        definition = AgentDefinition(
            name="reasoning-agent",
            capabilities=[
                Capability(intent=IntentRef("ReasonIntent"))
            ],
        )
        super().__init__(definition, router)

    # ----------------------------------------------------------
    # Main Handler
    # ----------------------------------------------------------
    def handle_intent(self, env) -> AgentResponse:
        summary = env.payload.get("summary", "")

        if not isinstance(summary, str) or not summary.strip():
            return AgentResponse.failure(
                self.error("Missing 'summary' for reasoning step"),
                agent=self.definition.name,
                trace_id=env.metadata.traceId,
            )

        reasoning = self._derive_reasoning(summary)

        return AgentResponse.success(
            {"reasoning": reasoning},
            agent=self.definition.name,
            trace_id=env.metadata.traceId,
        )

    # ----------------------------------------------------------
    # Deterministic faux reasoning engine
    # ----------------------------------------------------------
    def _derive_reasoning(self, summary: str) -> str:
        """
        Produce simple deterministic inferences based on keywords.
        This keeps the entire demo offline and predictable.
        """

        s = summary.lower()

        insights = []

        if "advantage" in s or "benefit" in s:
            insights.append("The topic includes notable advantages worth considering.")

        if "challenge" in s or "problem" in s:
            insights.append("There are challenges associated with the topic.")

        if "application" in s or "use case" in s:
            insights.append("The topic has practical real-world applications.")

        if not insights:
            insights.append("The topic contains general information without strong signals.")

        return " ".join(insights)
