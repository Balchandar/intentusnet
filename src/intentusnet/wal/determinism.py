"""
Determinism enforcement and verification.

Tracks input/output hashes for agent invocations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
from enum import Enum
import hashlib
import json


class DeterminismPolicy(str, Enum):
    """Determinism enforcement policy."""
    FAIL = "fail"              # Fail on determinism violation
    WARN = "warn"              # Log warning, continue
    RECORD_ONLY = "record_only"  # Record but don't enforce


@dataclass
class InvocationBoundary:
    """
    Agent invocation determinism boundary.

    Captures input/output hashes for replay verification.
    """
    agent_name: str
    step_id: str
    input_hash: str
    output_hash: Optional[str] = None
    agent_version: Optional[str] = None

    def compute_input_hash(self, input_data: Any) -> str:
        """Compute deterministic input hash."""
        canonical = json.dumps(
            input_data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def compute_output_hash(self, output_data: Any) -> str:
        """Compute deterministic output hash."""
        canonical = json.dumps(
            output_data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "step_id": self.step_id,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "agent_version": self.agent_version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InvocationBoundary":
        return cls(
            agent_name=data["agent_name"],
            step_id=data["step_id"],
            input_hash=data["input_hash"],
            output_hash=data.get("output_hash"),
            agent_version=data.get("agent_version"),
        )


@dataclass
class DeterminismViolation:
    """Determinism violation record."""
    execution_id: str
    step_id: str
    violation_type: str
    expected: str
    actual: str
    details: dict

    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "step_id": self.step_id,
            "violation_type": self.violation_type,
            "expected": self.expected,
            "actual": self.actual,
            "details": self.details,
        }


class DeterminismEnforcer:
    """
    Enforces determinism policy during replay.
    """

    def __init__(self, policy: DeterminismPolicy = DeterminismPolicy.FAIL) -> None:
        self.policy = policy
        self.violations: list[DeterminismViolation] = []

    def verify_input_hash(
        self,
        execution_id: str,
        step_id: str,
        expected_hash: str,
        actual_hash: str,
    ) -> bool:
        """
        Verify input hash matches.

        Returns True if match, raises or logs violation based on policy.
        """
        if expected_hash == actual_hash:
            return True

        violation = DeterminismViolation(
            execution_id=execution_id,
            step_id=step_id,
            violation_type="input_hash_mismatch",
            expected=expected_hash,
            actual=actual_hash,
            details={},
        )

        self.violations.append(violation)

        if self.policy == DeterminismPolicy.FAIL:
            raise DeterminismError(
                f"Input hash mismatch for step {step_id}: "
                f"expected {expected_hash}, got {actual_hash}"
            )
        elif self.policy == DeterminismPolicy.WARN:
            import logging
            logging.warning(
                f"Input hash mismatch for step {step_id}: "
                f"expected {expected_hash}, got {actual_hash}"
            )

        return False

    def verify_output_hash(
        self,
        execution_id: str,
        step_id: str,
        expected_hash: str,
        actual_hash: str,
    ) -> bool:
        """
        Verify output hash matches.

        Returns True if match, raises or logs violation based on policy.
        """
        if expected_hash == actual_hash:
            return True

        violation = DeterminismViolation(
            execution_id=execution_id,
            step_id=step_id,
            violation_type="output_hash_mismatch",
            expected=expected_hash,
            actual=actual_hash,
            details={},
        )

        self.violations.append(violation)

        if self.policy == DeterminismPolicy.FAIL:
            raise DeterminismError(
                f"Output hash mismatch for step {step_id}: "
                f"expected {expected_hash}, got {actual_hash}"
            )
        elif self.policy == DeterminismPolicy.WARN:
            import logging
            logging.warning(
                f"Output hash mismatch for step {step_id}: "
                f"expected {expected_hash}, got {actual_hash}"
            )

        return False

    def has_violations(self) -> bool:
        """Check if any violations occurred."""
        return len(self.violations) > 0

    def get_violations(self) -> list[DeterminismViolation]:
        """Get all violations."""
        return list(self.violations)


class DeterminismError(Exception):
    """Raised when determinism violation occurs in FAIL mode."""
    pass
