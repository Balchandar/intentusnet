"""
Cost estimation models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from enum import Enum


class ResourceType(str, Enum):
    """
    Resource types for cost accounting.
    """

    # Compute
    CPU_MS = "cpu_ms"  # CPU milliseconds
    MEMORY_MB_MS = "memory_mb_ms"  # Memory MB-milliseconds

    # LLM costs
    LLM_INPUT_TOKENS = "llm_input_tokens"
    LLM_OUTPUT_TOKENS = "llm_output_tokens"

    # Network
    NETWORK_BYTES = "network_bytes"

    # Storage
    STORAGE_WRITES = "storage_writes"
    STORAGE_READS = "storage_reads"

    # Agent invocations
    AGENT_CALLS = "agent_calls"


@dataclass
class CostModel:
    """
    Cost model for an agent or operation.

    Defines unit costs for different resource types.
    """

    # Resource costs (in arbitrary cost units)
    costs: Dict[ResourceType, float] = field(default_factory=dict)

    # Base cost (fixed overhead)
    base_cost: float = 0.0

    def estimate_cost(self, usage: Dict[ResourceType, float]) -> float:
        """
        Estimate cost based on usage.
        """
        total = self.base_cost

        for resource, amount in usage.items():
            unit_cost = self.costs.get(resource, 0.0)
            total += unit_cost * amount

        return total

    def to_dict(self) -> Dict[str, Any]:
        return {
            "costs": {k.value: v for k, v in self.costs.items()},
            "base_cost": self.base_cost,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CostModel:
        return cls(
            costs={ResourceType(k): v for k, v in data.get("costs", {}).items()},
            base_cost=data.get("base_cost", 0.0),
        )


@dataclass
class CostEstimate:
    """
    Pre-execution cost estimate.
    """

    # Execution context
    execution_id: str
    intent_name: str

    # Estimated resource usage
    estimated_usage: Dict[ResourceType, float] = field(default_factory=dict)

    # Estimated total cost (in cost units)
    estimated_cost: float = 0.0

    # Budget constraint
    budget_limit: Optional[float] = None
    exceeds_budget: bool = False

    # Step-level breakdown
    step_estimates: Dict[str, float] = field(default_factory=dict)

    # Metadata
    estimation_method: str = "static_analysis"
    confidence: float = 1.0  # 0.0 to 1.0

    # Actual (recorded after execution)
    actual_usage: Optional[Dict[ResourceType, float]] = None
    actual_cost: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "intent_name": self.intent_name,
            "estimated_usage": {k.value: v for k, v in self.estimated_usage.items()},
            "estimated_cost": self.estimated_cost,
            "budget_limit": self.budget_limit,
            "exceeds_budget": self.exceeds_budget,
            "step_estimates": self.step_estimates,
            "estimation_method": self.estimation_method,
            "confidence": self.confidence,
            "actual_usage": (
                {k.value: v for k, v in self.actual_usage.items()} if self.actual_usage else None
            ),
            "actual_cost": self.actual_cost,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CostEstimate:
        return cls(
            execution_id=data["execution_id"],
            intent_name=data["intent_name"],
            estimated_usage={
                ResourceType(k): v for k, v in data.get("estimated_usage", {}).items()
            },
            estimated_cost=data.get("estimated_cost", 0.0),
            budget_limit=data.get("budget_limit"),
            exceeds_budget=data.get("exceeds_budget", False),
            step_estimates=data.get("step_estimates", {}),
            estimation_method=data.get("estimation_method", "static_analysis"),
            confidence=data.get("confidence", 1.0),
            actual_usage=(
                {ResourceType(k): v for k, v in data["actual_usage"].items()}
                if data.get("actual_usage")
                else None
            ),
            actual_cost=data.get("actual_cost"),
        )
