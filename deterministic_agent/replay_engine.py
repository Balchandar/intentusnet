"""
IntentusNet v1.4.1 Deterministic Agent - Replay Engine

Replay engine for deterministic diff and verification.

This engine provides:
- Execution replay from WAL
- Deterministic diff between executions
- Logic drift detection and classification
- Fingerprint verification

STRICT PASS RULE (EXCELLENT MODE):
A test PASSES only if ALL match:
1. Intent
2. Tool
3. Param hash
4. Execution order
5. Side-effect class
6. Output hash
7. Retry pattern
8. Execution fingerprint
9. WAL resume branch
10. Timeout / latency determinism

Any mismatch is classified as Logic Drift.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, List

from .models import (
    WALEntry,
    ExecutionFingerprint,
    SideEffectClass,
    RetryReason,
    LatencyMetadata,
    DriftClassification,
)
from .wal_engine import WALReader, WALIntegrityError


@dataclass
class ReplayStep:
    """
    Reconstructed step from WAL for replay comparison.
    """
    step_id: str
    intent: str
    tool_name: str
    execution_order: int
    params_hash: str
    output_hash: str
    side_effect_class: SideEffectClass
    retry_count: int
    retry_reason: RetryReason
    timeout_ms: int
    did_timeout: bool
    committed: bool

    @classmethod
    def from_wal_entries(
        cls,
        started: dict[str, Any],
        committed: Optional[dict[str, Any]] = None,
    ) -> ReplayStep:
        """Create from WAL entries."""
        latency = started.get("latency_metadata", {})

        return cls(
            step_id=started.get("step_id", ""),
            intent=started.get("intent", ""),
            tool_name=started.get("tool_name", ""),
            execution_order=started.get("execution_order", 0),
            params_hash=started.get("params_hash", ""),
            output_hash=committed.get("output_hash", "") if committed else "",
            side_effect_class=SideEffectClass(
                started.get("side_effect_class", "read_only")
            ),
            retry_count=committed.get("retry_count", 0) if committed else 0,
            retry_reason=RetryReason(
                committed.get("retry_reason", "none") if committed else "none"
            ),
            timeout_ms=latency.get("timeout_ms", 0),
            did_timeout=latency.get("did_timeout", False),
            committed=committed is not None,
        )


@dataclass
class ReplayExecution:
    """
    Reconstructed execution from WAL.
    """
    execution_id: str
    steps: list[ReplayStep] = field(default_factory=list)
    fingerprint: str = ""
    completed: bool = False
    aborted: bool = False

    def get_intent_sequence(self) -> list[str]:
        return [s.intent for s in self.steps]

    def get_tool_sequence(self) -> list[str]:
        return [s.tool_name for s in self.steps]

    def get_param_hashes(self) -> list[str]:
        return [s.params_hash for s in self.steps]

    def get_output_hashes(self) -> list[str]:
        return [s.output_hash for s in self.steps]

    def get_retry_pattern(self) -> list[tuple[int, str]]:
        return [(s.retry_count, s.retry_reason.value) for s in self.steps]

    def get_execution_order(self) -> list[int]:
        return [s.execution_order for s in self.steps]

    def get_timeout_values(self) -> list[int]:
        return [s.timeout_ms for s in self.steps]

    def get_timeout_flags(self) -> list[bool]:
        return [s.did_timeout for s in self.steps]


@dataclass
class DiffResult:
    """
    Result of deterministic diff between two executions.
    """
    match: bool
    expected_fingerprint: str
    actual_fingerprint: str
    drifts: list[DriftClassification] = field(default_factory=list)

    @property
    def has_critical_drift(self) -> bool:
        """Check if any drift is critical (side-effect drift)."""
        return any(d.is_critical for d in self.drifts)

    @property
    def drift_summary(self) -> dict[str, int]:
        """Count drifts by type."""
        summary = {}
        for drift in self.drifts:
            key = drift.drift_type.value
            summary[key] = summary.get(key, 0) + 1
        return summary

    def to_dict(self) -> dict[str, Any]:
        return {
            "match": self.match,
            "expected_fingerprint": self.expected_fingerprint,
            "actual_fingerprint": self.actual_fingerprint,
            "has_critical_drift": self.has_critical_drift,
            "drift_count": len(self.drifts),
            "drift_summary": self.drift_summary,
            "drifts": [d.to_dict() for d in self.drifts],
        }


class ReplayEngine:
    """
    Replay engine for deterministic execution verification.

    USAGE:
        engine = ReplayEngine()

        # Load executions from WAL
        expected = engine.load_from_wal("./logs/expected.jsonl")
        actual = engine.load_from_wal("./logs/actual.jsonl")

        # Compare executions
        diff = engine.diff(expected, actual)

        if diff.match:
            print("Executions are deterministically equivalent")
        else:
            print(f"Drift detected: {diff.drift_summary}")
    """

    def load_from_wal(self, wal_path: str) -> ReplayExecution:
        """
        Load execution from WAL file.

        Args:
            wal_path: Path to WAL file

        Returns:
            ReplayExecution reconstructed from WAL
        """
        reader = WALReader(wal_path)
        reader.load()

        entries = reader.get_entries()
        if not entries:
            raise WALIntegrityError("Empty WAL file")

        execution_id = entries[0].get("execution_id", "")
        execution = ReplayExecution(execution_id=execution_id)

        # Group entries by step
        step_started: dict[str, dict] = {}
        step_committed: dict[str, dict] = {}

        for entry in entries:
            entry_type = entry.get("entry_type")
            step_id = entry.get("step_id")

            if entry_type == "step.started":
                step_started[step_id] = entry
            elif entry_type == "step.committed":
                step_committed[step_id] = entry
            elif entry_type == "execution.completed":
                execution.completed = True
                execution.fingerprint = entry.get("fingerprint", "")
            elif entry_type == "execution.aborted":
                execution.aborted = True

        # Build steps
        for step_id, started in step_started.items():
            committed = step_committed.get(step_id)
            step = ReplayStep.from_wal_entries(started, committed)
            execution.steps.append(step)

        # Sort by execution order
        execution.steps.sort(key=lambda s: s.execution_order)

        return execution

    def diff(
        self,
        expected: ReplayExecution,
        actual: ReplayExecution,
    ) -> DiffResult:
        """
        Compare two executions for deterministic equivalence.

        STRICT PASS RULE:
        All of the following must match for a PASS:
        1. Intent sequence
        2. Tool sequence
        3. Param hashes
        4. Execution order
        5. Side-effect classes
        6. Output hashes
        7. Retry pattern
        8. Execution fingerprint
        9. WAL resume branch (completion state)
        10. Timeout / latency determinism

        Args:
            expected: Expected execution (golden)
            actual: Actual execution (test run)

        Returns:
            DiffResult with match status and any drifts
        """
        drifts = []

        # Compare step count
        if len(expected.steps) != len(actual.steps):
            drifts.append(DriftClassification(
                drift_type=DriftClassification.DriftType.EXECUTION_DRIFT,
                expected_value=len(expected.steps),
                actual_value=len(actual.steps),
                step_id="global",
            ))

        # Compare each step
        for i, (exp_step, act_step) in enumerate(
            zip(expected.steps, actual.steps)
        ):
            step_drifts = self._compare_steps(exp_step, act_step)
            drifts.extend(step_drifts)

        # Compare fingerprints
        if expected.fingerprint != actual.fingerprint:
            drifts.append(DriftClassification(
                drift_type=DriftClassification.DriftType.EXECUTION_DRIFT,
                expected_value=expected.fingerprint,
                actual_value=actual.fingerprint,
                step_id="global",
            ))

        # Compare completion state
        if expected.completed != actual.completed:
            drifts.append(DriftClassification(
                drift_type=DriftClassification.DriftType.EXECUTION_DRIFT,
                expected_value=expected.completed,
                actual_value=actual.completed,
                step_id="global",
            ))

        match = len(drifts) == 0

        return DiffResult(
            match=match,
            expected_fingerprint=expected.fingerprint,
            actual_fingerprint=actual.fingerprint,
            drifts=drifts,
        )

    def _compare_steps(
        self,
        expected: ReplayStep,
        actual: ReplayStep,
    ) -> list[DriftClassification]:
        """Compare two steps for drift."""
        drifts = []
        step_id = expected.step_id

        # 1. Intent drift
        if expected.intent != actual.intent:
            drifts.append(DriftClassification(
                drift_type=DriftClassification.DriftType.INTENT_DRIFT,
                expected_value=expected.intent,
                actual_value=actual.intent,
                step_id=step_id,
            ))

        # 2. Tool drift
        if expected.tool_name != actual.tool_name:
            drifts.append(DriftClassification(
                drift_type=DriftClassification.DriftType.TOOL_DRIFT,
                expected_value=expected.tool_name,
                actual_value=actual.tool_name,
                step_id=step_id,
            ))

        # 3. Param drift
        if expected.params_hash != actual.params_hash:
            drifts.append(DriftClassification(
                drift_type=DriftClassification.DriftType.PARAM_DRIFT,
                expected_value=expected.params_hash,
                actual_value=actual.params_hash,
                step_id=step_id,
            ))

        # 4. Execution order drift
        if expected.execution_order != actual.execution_order:
            drifts.append(DriftClassification(
                drift_type=DriftClassification.DriftType.EXECUTION_DRIFT,
                expected_value=expected.execution_order,
                actual_value=actual.execution_order,
                step_id=step_id,
            ))

        # 5. Side-effect drift (CRITICAL)
        if expected.side_effect_class != actual.side_effect_class:
            drifts.append(DriftClassification(
                drift_type=DriftClassification.DriftType.SIDE_EFFECT_DRIFT,
                expected_value=expected.side_effect_class.value,
                actual_value=actual.side_effect_class.value,
                step_id=step_id,
            ))

        # 6. Output drift
        if expected.output_hash != actual.output_hash:
            drifts.append(DriftClassification(
                drift_type=DriftClassification.DriftType.OUTPUT_DRIFT,
                expected_value=expected.output_hash,
                actual_value=actual.output_hash,
                step_id=step_id,
            ))

        # 7. Retry drift
        if (expected.retry_count, expected.retry_reason) != (actual.retry_count, actual.retry_reason):
            drifts.append(DriftClassification(
                drift_type=DriftClassification.DriftType.RETRY_DRIFT,
                expected_value=(expected.retry_count, expected.retry_reason.value),
                actual_value=(actual.retry_count, actual.retry_reason.value),
                step_id=step_id,
            ))

        # 8. Timeout drift
        if expected.timeout_ms != actual.timeout_ms or expected.did_timeout != actual.did_timeout:
            drifts.append(DriftClassification(
                drift_type=DriftClassification.DriftType.TIMEOUT_DRIFT,
                expected_value=(expected.timeout_ms, expected.did_timeout),
                actual_value=(actual.timeout_ms, actual.did_timeout),
                step_id=step_id,
            ))

        return drifts

    def compute_reliability(
        self,
        results: list[DiffResult],
    ) -> dict[str, Any]:
        """
        Compute reliability metrics from diff results.

        Returns:
            Dict with:
            - reliability: Passed / Total ratio
            - drift_counts: Count by drift type
            - critical_failures: Count of critical (side-effect) drifts
        """
        total = len(results)
        passed = sum(1 for r in results if r.match)

        drift_counts: dict[str, int] = {}
        critical_failures = 0

        for result in results:
            if result.has_critical_drift:
                critical_failures += 1

            for drift_type, count in result.drift_summary.items():
                drift_counts[drift_type] = drift_counts.get(drift_type, 0) + count

        return {
            "total_tests": total,
            "passed": passed,
            "failed": total - passed,
            "reliability": passed / total if total > 0 else 0.0,
            "drift_counts": drift_counts,
            "critical_failures": critical_failures,
        }


def create_replay_engine() -> ReplayEngine:
    """Factory function to create replay engine."""
    return ReplayEngine()
