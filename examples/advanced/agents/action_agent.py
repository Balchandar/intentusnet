from __future__ import annotations

from typing import Any, Dict

from intentusnet.core.agent import BaseAgent
from intentusnet.protocol import AgentDefinition, Capability, IntentRef, AgentResponse

class ActionAgent(BaseAgent):
    """
    Final step agent that simulates performing an "action" based on reasoning.

    Input:
        { "reasoning": "..." }

    Output:
        { "action": "Action taken: ..." }
    """

    def __init__(self, router):
        definition = AgentDefinition(
            name="action-agent",
            capabilities=[
                Capability(intent=IntentRef("ActionIntent"))
            ],
        )
        super().__init__(definition, router)

    # ----------------------------------------------------------
    # Main handler
    # ----------------------------------------------------------
    def handle_intent(self, env) -> AgentResponse:
        reasoning = env.payload.get("reasoning", "")

        if not isinstance(reasoning, str) or not reasoning.strip():
            return AgentResponse.failure(
                self.error("Missing 'reasoning' for ActionIntent"),
                agent=self.definition.name,
                trace_id=env.metadata.traceId,
            )

        result = self._simulate_action(reasoning)

        return AgentResponse.success(
            {"action": result},
            agent=self.definition.name,
            trace_id=env.metadata.traceId,
        )

    # ----------------------------------------------------------
    # Deterministic simulated action
    # ----------------------------------------------------------
    def _simulate_action(self, reasoning: str) -> str:
        """
        For demo:
            Convert reasoning into a pseudo-action confirmation.

        In real deployments:
            Could trigger workflow execution, DB update, RPA, API calls, etc.
        """
        return f"Action completed successfully based on reasoning: {reasoning[:80]}..."
