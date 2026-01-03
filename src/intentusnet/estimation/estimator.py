"""
Cost estimator - Pre-execution cost estimation.
"""

from __future__ import annotations

import sys
from typing import Dict, Any, Optional

from intentusnet.protocol.intent import IntentEnvelope

from .models import CostEstimate, CostModel, ResourceType


class CostEstimator:
    """
    Estimates execution cost before running.

    Uses deterministic model based on:
    - Payload size
    - Agent count
    - Routing strategy
    - Historical data (if available)
    """

    def __init__(self, agent_cost_models: Optional[Dict[str, CostModel]] = None) -> None:
        """
        Initialize cost estimator.

        Args:
            agent_cost_models: Cost models per agent name
        """
        self.agent_cost_models = agent_cost_models or {}

    def estimate(
        self,
        envelope: IntentEnvelope,
        execution_id: str,
        agent_names: list[str],
        budget_limit: Optional[float] = None,
    ) -> CostEstimate:
        """
        Estimate execution cost.

        Returns CostEstimate with usage and cost breakdown.
        """
        estimate = CostEstimate(
            execution_id=execution_id,
            intent_name=envelope.intent.name,
            budget_limit=budget_limit,
        )

        # Estimate payload size
        payload_size = self._estimate_payload_size(envelope)
        estimate.estimated_usage[ResourceType.NETWORK_BYTES] = payload_size

        # Estimate agent calls
        agent_call_count = len(agent_names)
        estimate.estimated_usage[ResourceType.AGENT_CALLS] = agent_call_count

        # Estimate per-agent costs
        total_cost = 0.0
        for agent_name in agent_names:
            agent_cost = self._estimate_agent_cost(agent_name, envelope)
            estimate.step_estimates[agent_name] = agent_cost
            total_cost += agent_cost

        # Add network overhead
        network_cost = payload_size * 0.001  # 0.001 cost units per byte
        total_cost += network_cost

        estimate.estimated_cost = total_cost

        # Check budget
        if budget_limit is not None:
            estimate.exceeds_budget = total_cost > budget_limit

        return estimate

    def _estimate_payload_size(self, envelope: IntentEnvelope) -> float:
        """
        Estimate payload size in bytes.
        """
        # Rough estimate using sys.getsizeof on parameters
        params = getattr(envelope.intent, "parameters", {})
        if not params:
            return 100.0  # Base overhead

        try:
            size = sys.getsizeof(str(params))
            return float(size)
        except Exception:
            return 1000.0  # Default estimate

    def _estimate_agent_cost(self, agent_name: str, envelope: IntentEnvelope) -> float:
        """
        Estimate cost for a single agent call.
        """
        cost_model = self.agent_cost_models.get(agent_name)

        if cost_model is None:
            # Default cost model
            return 10.0  # Base cost units per agent call

        # Use agent-specific cost model
        usage = {
            ResourceType.AGENT_CALLS: 1.0,
        }

        # Estimate LLM token usage (if applicable)
        params = getattr(envelope.intent, "parameters", {})
        param_str = str(params)
        estimated_input_tokens = len(param_str.split()) * 1.3  # Rough tokenization
        usage[ResourceType.LLM_INPUT_TOKENS] = estimated_input_tokens

        # Assume 2x output tokens (heuristic)
        usage[ResourceType.LLM_OUTPUT_TOKENS] = estimated_input_tokens * 2.0

        return cost_model.estimate_cost(usage)

    def record_actual_cost(
        self,
        estimate: CostEstimate,
        actual_usage: Dict[ResourceType, float],
        actual_cost: float,
    ) -> CostEstimate:
        """
        Record actual cost after execution.
        """
        estimate.actual_usage = actual_usage
        estimate.actual_cost = actual_cost
        return estimate
