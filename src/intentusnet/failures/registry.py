"""
Failure registry and query interface.
"""

from __future__ import annotations

from typing import List, Optional
from pathlib import Path
import json

from .models import StructuredFailure, FailureType


class FailureRegistry:
    """
    In-memory registry of failures for an execution.

    Can be persisted to disk for post-mortem analysis.
    """

    def __init__(self, execution_id: str) -> None:
        self.execution_id = execution_id
        self.failures: List[StructuredFailure] = []

    def record(self, failure: StructuredFailure) -> None:
        """
        Record a failure.
        """
        self.failures.append(failure)

    def get_all(self) -> List[StructuredFailure]:
        """
        Get all failures.
        """
        return list(self.failures)

    def get_by_type(self, failure_type: FailureType) -> List[StructuredFailure]:
        """
        Query failures by type.
        """
        return [f for f in self.failures if f.failure_type == failure_type]

    def get_by_step(self, step_id: str) -> List[StructuredFailure]:
        """
        Query failures by step.
        """
        return [f for f in self.failures if f.step_id == step_id]

    def get_recoverable(self) -> List[StructuredFailure]:
        """
        Get all recoverable failures.
        """
        return [f for f in self.failures if f.recoverable]

    def get_non_recoverable(self) -> List[StructuredFailure]:
        """
        Get all non-recoverable failures.
        """
        return [f for f in self.failures if not f.recoverable]

    def has_failures(self) -> bool:
        """
        Check if any failures recorded.
        """
        return len(self.failures) > 0

    def to_dict(self) -> dict:
        """
        Serialize to dict.
        """
        return {
            "execution_id": self.execution_id,
            "failures": [f.to_dict() for f in self.failures],
        }

    def save(self, path: Path) -> None:
        """
        Save to file.
        """
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> FailureRegistry:
        """
        Deserialize from dict.
        """
        registry = cls(execution_id=data["execution_id"])
        for failure_data in data.get("failures", []):
            failure = StructuredFailure.from_dict(failure_data)
            registry.record(failure)
        return registry

    @classmethod
    def load(cls, path: Path) -> FailureRegistry:
        """
        Load from file.
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
