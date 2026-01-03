"""
Contract and side-effect models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal
from enum import Enum


class SideEffectClass(str, Enum):
    """
    Side-effect classification (must be declared per-step).

    Rules:
    - read_only: No state changes (safe to replay)
    - reversible: Changes can be undone (retry allowed)
    - irreversible: Cannot be undone (NO retry, WAL required)
    """

    READ_ONLY = "read_only"
    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"


@dataclass
class ExecutionContract:
    """
    Execution contract for a single step.

    All contracts are runtime-enforced.
    Violations cause execution to fail explicitly.
    """

    # Exactly-once semantics
    exactly_once: bool = False

    # Retry control
    no_retry: bool = False
    max_retries: Optional[int] = None

    # Idempotency requirement
    idempotent_required: bool = False

    # Timeout (milliseconds)
    timeout_ms: Optional[int] = None

    # Budget constraints
    max_cost_units: Optional[int] = None

    def to_dict(self) -> dict:
        """
        Serialize to dict for WAL/storage.
        """
        return {
            "exactly_once": self.exactly_once,
            "no_retry": self.no_retry,
            "max_retries": self.max_retries,
            "idempotent_required": self.idempotent_required,
            "timeout_ms": self.timeout_ms,
            "max_cost_units": self.max_cost_units,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ExecutionContract:
        """
        Deserialize from dict.
        """
        return cls(
            exactly_once=data.get("exactly_once", False),
            no_retry=data.get("no_retry", False),
            max_retries=data.get("max_retries"),
            idempotent_required=data.get("idempotent_required", False),
            timeout_ms=data.get("timeout_ms"),
            max_cost_units=data.get("max_cost_units"),
        )


@dataclass
class StepMetadata:
    """
    Metadata for a single execution step.

    Includes:
    - Step identity
    - Agent information
    - Side-effect classification
    - Contracts
    - Input/output hashes
    """

    step_id: str
    agent_name: str
    agent_version: Optional[str] = None

    # Side-effect classification (REQUIRED)
    side_effect: SideEffectClass = SideEffectClass.READ_ONLY

    # Contracts
    contract: ExecutionContract = field(default_factory=ExecutionContract)

    # Input/output
    input_hash: Optional[str] = None
    output_hash: Optional[str] = None

    # Execution metadata
    attempt_number: int = 1
    execution_time_ms: Optional[int] = None
    success: bool = False

    def to_dict(self) -> dict:
        """
        Serialize to dict.
        """
        return {
            "step_id": self.step_id,
            "agent_name": self.agent_name,
            "agent_version": self.agent_version,
            "side_effect": self.side_effect.value,
            "contract": self.contract.to_dict(),
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "attempt_number": self.attempt_number,
            "execution_time_ms": self.execution_time_ms,
            "success": self.success,
        }

    @classmethod
    def from_dict(cls, data: dict) -> StepMetadata:
        """
        Deserialize from dict.
        """
        return cls(
            step_id=data["step_id"],
            agent_name=data["agent_name"],
            agent_version=data.get("agent_version"),
            side_effect=SideEffectClass(data.get("side_effect", "read_only")),
            contract=ExecutionContract.from_dict(data.get("contract", {})),
            input_hash=data.get("input_hash"),
            output_hash=data.get("output_hash"),
            attempt_number=data.get("attempt_number", 1),
            execution_time_ms=data.get("execution_time_ms"),
            success=data.get("success", False),
        )


@dataclass
class ContractViolation:
    """
    Contract violation record.
    """

    step_id: str
    contract_name: str
    reason: str
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "contract_name": self.contract_name,
            "reason": self.reason,
            "details": self.details,
        }
