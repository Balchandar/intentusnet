"""
Structured failure models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Any, Dict
from enum import Enum


class FailureType(str, Enum):
    """
    Typed failure classification.

    No untyped exceptions allowed.
    """

    # Contract violations
    CONTRACT_VIOLATION = "contract_violation"
    TIMEOUT = "timeout"
    BUDGET_EXCEEDED = "budget_exceeded"

    # Routing failures
    NO_AGENT_FOUND = "no_agent_found"
    ROUTING_ERROR = "routing_error"
    FALLBACK_EXHAUSTED = "fallback_exhausted"

    # Agent failures
    AGENT_ERROR = "agent_error"
    AGENT_CRASHED = "agent_crashed"
    AGENT_UNAVAILABLE = "agent_unavailable"

    # Input validation
    INVALID_INPUT = "invalid_input"
    SCHEMA_VALIDATION_ERROR = "schema_validation_error"

    # WAL/Recovery failures
    WAL_INTEGRITY_ERROR = "wal_integrity_error"
    RECOVERY_ERROR = "recovery_error"

    # Side-effect violations
    IRREVERSIBLE_STEP_FAILED = "irreversible_step_failed"
    SIDE_EFFECT_VIOLATION = "side_effect_violation"

    # Infrastructure
    TRANSPORT_ERROR = "transport_error"
    NETWORK_ERROR = "network_error"

    # Unknown (should be rare)
    UNKNOWN = "unknown"


class RecoveryStrategy(str, Enum):
    """
    Recovery strategy for a failure.
    """

    RETRY = "retry"  # Can retry immediately
    RETRY_AFTER_DELAY = "retry_after_delay"  # Can retry after delay
    FALLBACK = "fallback"  # Try next agent in fallback chain
    ABORT = "abort"  # Cannot recover, abort execution
    MANUAL_INTERVENTION = "manual_intervention"  # Requires operator action


@dataclass
class StructuredFailure:
    """
    Structured failure record.

    All failures are typed, structured, and queryable.
    """

    # Classification
    failure_type: FailureType

    # Context
    execution_id: str
    
    # Details
    reason: str
    
    step_id: Optional[str] = None
    agent_name: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    # Recovery
    recoverable: bool = False
    recovery_strategy: Optional[RecoveryStrategy] = None

    # Causality
    caused_by: Optional[StructuredFailure] = None

    # Timestamp
    timestamp_iso: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize to dict.
        """
        return {
            "failure_type": self.failure_type.value,
            "execution_id": self.execution_id,
            "step_id": self.step_id,
            "agent_name": self.agent_name,
            "reason": self.reason,
            "details": self.details,
            "recoverable": self.recoverable,
            "recovery_strategy": self.recovery_strategy.value if self.recovery_strategy else None,
            "caused_by": self.caused_by.to_dict() if self.caused_by else None,
            "timestamp_iso": self.timestamp_iso,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StructuredFailure:
        """
        Deserialize from dict.
        """
        caused_by = None
        if data.get("caused_by"):
            caused_by = cls.from_dict(data["caused_by"])

        return cls(
            failure_type=FailureType(data["failure_type"]),
            execution_id=data["execution_id"],
            step_id=data.get("step_id"),
            agent_name=data.get("agent_name"),
            reason=data["reason"],
            details=data.get("details", {}),
            recoverable=data.get("recoverable", False),
            recovery_strategy=(
                RecoveryStrategy(data["recovery_strategy"])
                if data.get("recovery_strategy")
                else None
            ),
            caused_by=caused_by,
            timestamp_iso=data.get("timestamp_iso"),
        )

    def __str__(self) -> str:
        """
        Human-readable representation.
        """
        parts = [f"[{self.failure_type.value}]"]
        if self.step_id:
            parts.append(f"step={self.step_id}")
        if self.agent_name:
            parts.append(f"agent={self.agent_name}")
        parts.append(self.reason)

        return " ".join(parts)
