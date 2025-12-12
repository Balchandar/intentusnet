from __future__ import annotations

from typing import Dict, Any

from intentusnet.core.agent import BaseAgent
from intentusnet.protocol import AgentDefinition, Capability, IntentRef, AgentResponse


class ComparisonOrchestratorAgent(BaseAgent):
    """
    Orchestrates a side-by-side comparison between two topics.

    Pipeline:
        researchA = ResearchIntent(a)
        researchB = ResearchIntent(b)

    Combines both summaries into a comparison output.
    """

    def __init__(self, router):
        definition = AgentDefinition(
            name="comparison-orchestrator",
            capabilities=[
                Capability(intent=IntentRef("CompareIntent"))
            ],
        )
        super().__init__(definition, router)

    # ----------------------------------------------------------
    # Main Handler
    # ----------------------------------------------------------
    def handle_intent(self, env) -> AgentResponse:
        a = env.payload.get("a", "").strip()
        b = env.payload.get("b", "").strip()

        if not a or not b:
            return AgentResponse.failure(
                self.error("Missing fields 'a' and 'b'"),
                agent=self.definition.name,
                trace_id=env.metadata.traceId,
            )

        # Research A
        resA = self.emit_intent("ResearchIntent", {"topic": a})
        if resA.status == "error":
            return resA

        summaryA = resA.payload.get("summary", "")

        # Research B
        resB = self.emit_intent("ResearchIntent", {"topic": b})
        if resB.status == "error":
            return resB

        summaryB = resB.payload.get("summary", "")

        comparison = {
            "topicA": a,
            "topicB": b,
            "summaryA": summaryA,
            "summaryB": summaryB,
            "comparison": self._build_comparison(summaryA, summaryB),
        }

        return AgentResponse.success(
            comparison,
            agent=self.definition.name,
            trace_id=env.metadata.traceId,
        )

    # ----------------------------------------------------------
    # Helper for building comparison text
    # ----------------------------------------------------------
    def _build_comparison(self, summaryA: str, summaryB: str) -> str:
        """
        Naive comparison for demo purposes.
        """
        return (
            "Comparison between topics:\n\n"
            f"A: {summaryA}\n\n"
            f"B: {summaryB}\n"
        )
