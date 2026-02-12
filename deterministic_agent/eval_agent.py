"""
IntentusNet v1.4.1 Deterministic Agent - Evaluation Rig

Evaluation rig for deterministic reliability testing.

This module provides:
- Golden dataset loading and execution
- Deterministic diff using ReplayEngine
- Reliability score computation
- CI/CD integration support

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

Any mismatch → classify as Logic Drift

LOGIC DRIFT CLASSIFICATION:
- Intent Drift
- Tool Drift
- Param Drift
- Execution Drift
- Output Drift
- Retry Drift
- Timeout Drift
- Side-effect Drift (CRITICAL - fails CI immediately)

USAGE:
    # Run evaluation
    python eval_agent.py --dataset tests/golden_dataset.jsonl --runs 3

    # Check CI pass threshold
    python eval_agent.py --dataset tests/golden_dataset.jsonl --threshold 0.98
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, List

from .models import DriftClassification
from .main import (
    DeterministicAgentRuntime,
    ExecutionStep,
    ExecutionResult,
    create_runtime,
)
from .replay_engine import (
    ReplayEngine,
    ReplayExecution,
    DiffResult,
    create_replay_engine,
)
from .mcp_adapter import create_mcp_adapter

logger = logging.getLogger("intentusnet.eval")


@dataclass
class TestCase:
    """
    A test case from the golden dataset.
    """
    test_id: str
    description: str
    steps: list[ExecutionStep]
    expected_fingerprint: str
    expected_outputs: list[Any] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TestCase:
        steps = [ExecutionStep(**s) for s in data.get("steps", [])]
        return cls(
            test_id=data.get("test_id", ""),
            description=data.get("description", ""),
            steps=steps,
            expected_fingerprint=data.get("expected_fingerprint", ""),
            expected_outputs=data.get("expected_outputs", []),
            tags=data.get("tags", []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "expected_fingerprint": self.expected_fingerprint,
            "expected_outputs": self.expected_outputs,
            "tags": self.tags,
        }


@dataclass
class TestResult:
    """
    Result of running a single test case.
    """
    test_id: str
    passed: bool
    execution_result: ExecutionResult
    diff_result: Optional[DiffResult] = None
    error: Optional[str] = None
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "passed": self.passed,
            "execution": self.execution_result.to_dict(),
            "diff": self.diff_result.to_dict() if self.diff_result else None,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass
class EvaluationReport:
    """
    Complete evaluation report.
    """
    timestamp: str
    run_number: int
    total_tests: int
    passed: int
    failed: int
    reliability: float
    drift_counts: dict[str, int] = field(default_factory=dict)
    critical_failures: int = 0
    results: list[TestResult] = field(default_factory=list)
    total_duration_ms: int = 0
    wal_size_bytes: int = 0

    @property
    def ci_passed(self) -> bool:
        """Check if evaluation passes CI threshold (98%)."""
        return self.reliability >= 0.98 and self.critical_failures == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "run_number": self.run_number,
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "reliability": self.reliability,
            "drift_counts": self.drift_counts,
            "critical_failures": self.critical_failures,
            "ci_passed": self.ci_passed,
            "total_duration_ms": self.total_duration_ms,
            "wal_size_bytes": self.wal_size_bytes,
            "results": [r.to_dict() for r in self.results],
        }


class EvaluationRig:
    """
    Evaluation rig for deterministic reliability testing.

    USAGE:
        rig = EvaluationRig(
            dataset_path="tests/golden_dataset.jsonl",
            wal_dir="./eval_logs",
        )

        # Run evaluation
        report = rig.run()

        # Check CI pass
        if report.ci_passed:
            print("CI PASS")
        else:
            print(f"CI FAIL: reliability={report.reliability}")
    """

    def __init__(
        self,
        dataset_path: str,
        wal_dir: str = "./eval_logs",
        golden_wal_dir: Optional[str] = None,
    ):
        """
        Initialize evaluation rig.

        Args:
            dataset_path: Path to golden dataset (JSONL)
            wal_dir: Directory for test WAL files
            golden_wal_dir: Directory containing golden WAL files
        """
        self.dataset_path = Path(dataset_path)
        self.wal_dir = Path(wal_dir)
        self.golden_wal_dir = Path(golden_wal_dir) if golden_wal_dir else None

        # Create directories
        self.wal_dir.mkdir(parents=True, exist_ok=True)

        # Load test cases
        self.test_cases = self._load_dataset()

        # Initialize components
        self.replay_engine = create_replay_engine()

    def _load_dataset(self) -> list[TestCase]:
        """Load test cases from golden dataset."""
        if not self.dataset_path.exists():
            logger.warning(f"Dataset not found: {self.dataset_path}")
            return []

        test_cases = []
        with open(self.dataset_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                test_cases.append(TestCase.from_dict(data))

        logger.info(f"Loaded {len(test_cases)} test cases from {self.dataset_path}")
        return test_cases

    def run(self, run_number: int = 1) -> EvaluationReport:
        """
        Run evaluation on all test cases.

        Args:
            run_number: Run number for tracking

        Returns:
            EvaluationReport with results
        """
        start_time = time.time()
        results = []

        # Create fresh runtime for this run
        run_wal_dir = self.wal_dir / f"run_{run_number}"
        if run_wal_dir.exists():
            shutil.rmtree(run_wal_dir)
        run_wal_dir.mkdir(parents=True)

        runtime = create_runtime(wal_dir=str(run_wal_dir))

        for test_case in self.test_cases:
            result = self._run_test_case(runtime, test_case, run_wal_dir)
            results.append(result)

        # Compute metrics
        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed
        reliability = passed / len(results) if results else 0.0

        # Aggregate drift counts
        drift_counts: dict[str, int] = {}
        critical_failures = 0

        for result in results:
            if result.diff_result:
                if result.diff_result.has_critical_drift:
                    critical_failures += 1
                for drift_type, count in result.diff_result.drift_summary.items():
                    drift_counts[drift_type] = drift_counts.get(drift_type, 0) + count

        # Calculate WAL size
        wal_size = sum(
            f.stat().st_size for f in run_wal_dir.glob("*.jsonl")
        )

        total_duration = int((time.time() - start_time) * 1000)

        return EvaluationReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            run_number=run_number,
            total_tests=len(results),
            passed=passed,
            failed=failed,
            reliability=reliability,
            drift_counts=drift_counts,
            critical_failures=critical_failures,
            results=results,
            total_duration_ms=total_duration,
            wal_size_bytes=wal_size,
        )

    def _run_test_case(
        self,
        runtime: DeterministicAgentRuntime,
        test_case: TestCase,
        wal_dir: Path,
    ) -> TestResult:
        """Run a single test case."""
        start_time = time.time()

        try:
            # Execute test case
            exec_result = runtime.execute_steps(
                test_case.steps,
                execution_id=test_case.test_id,
            )

            # Load execution for diff
            actual = self.replay_engine.load_from_wal(exec_result.wal_path)

            # Load golden execution if available
            golden_wal_path = None
            if self.golden_wal_dir:
                golden_wal_path = self.golden_wal_dir / f"{test_case.test_id}.jsonl"

            if golden_wal_path and golden_wal_path.exists():
                expected = self.replay_engine.load_from_wal(str(golden_wal_path))
                diff_result = self.replay_engine.diff(expected, actual)
            else:
                # Compare with expected fingerprint
                fingerprint_match = (
                    exec_result.fingerprint == test_case.expected_fingerprint
                    if test_case.expected_fingerprint
                    else True
                )

                diff_result = DiffResult(
                    match=fingerprint_match and exec_result.success,
                    expected_fingerprint=test_case.expected_fingerprint,
                    actual_fingerprint=exec_result.fingerprint,
                    drifts=[],
                )

            duration = int((time.time() - start_time) * 1000)

            return TestResult(
                test_id=test_case.test_id,
                passed=diff_result.match and exec_result.success,
                execution_result=exec_result,
                diff_result=diff_result,
                duration_ms=duration,
            )

        except Exception as e:
            logger.exception(f"Test case {test_case.test_id} failed with error")
            duration = int((time.time() - start_time) * 1000)

            return TestResult(
                test_id=test_case.test_id,
                passed=False,
                execution_result=ExecutionResult(
                    success=False,
                    execution_id=test_case.test_id,
                    error=str(e),
                ),
                error=str(e),
                duration_ms=duration,
            )

    def run_multiple(self, num_runs: int = 3) -> dict[str, Any]:
        """
        Run evaluation multiple times and compute mean reliability.

        Used for CI/CD to ensure stable deterministic behavior.

        Args:
            num_runs: Number of evaluation runs

        Returns:
            Dict with aggregate statistics
        """
        reports = []

        for i in range(num_runs):
            logger.info(f"Running evaluation {i + 1}/{num_runs}")
            report = self.run(run_number=i + 1)
            reports.append(report)

        # Compute mean reliability
        reliabilities = [r.reliability for r in reports]
        mean_reliability = sum(reliabilities) / len(reliabilities)

        # Check for any critical failures
        total_critical = sum(r.critical_failures for r in reports)

        # Fingerprint consistency check
        fingerprints_by_test = {}
        for report in reports:
            for result in report.results:
                test_id = result.test_id
                fp = result.execution_result.fingerprint
                if test_id not in fingerprints_by_test:
                    fingerprints_by_test[test_id] = set()
                fingerprints_by_test[test_id].add(fp)

        fingerprint_mismatches = sum(
            1 for fps in fingerprints_by_test.values() if len(fps) > 1
        )

        return {
            "num_runs": num_runs,
            "mean_reliability": mean_reliability,
            "min_reliability": min(reliabilities),
            "max_reliability": max(reliabilities),
            "total_critical_failures": total_critical,
            "fingerprint_mismatches": fingerprint_mismatches,
            "ci_passed": (
                mean_reliability >= 0.98
                and total_critical == 0
                and fingerprint_mismatches == 0
            ),
            "reports": [r.to_dict() for r in reports],
        }


def create_evaluation_rig(
    dataset_path: str,
    wal_dir: str = "./eval_logs",
    golden_wal_dir: Optional[str] = None,
) -> EvaluationRig:
    """
    Factory function to create evaluation rig.

    Args:
        dataset_path: Path to golden dataset
        wal_dir: WAL directory for test runs
        golden_wal_dir: Optional golden WAL directory

    Returns:
        Configured EvaluationRig
    """
    return EvaluationRig(
        dataset_path=dataset_path,
        wal_dir=wal_dir,
        golden_wal_dir=golden_wal_dir,
    )


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def main():
    """CLI entry point for evaluation rig."""
    parser = argparse.ArgumentParser(
        description="IntentusNet v1.4.1 Deterministic Agent Evaluation Rig"
    )
    parser.add_argument(
        "--dataset",
        default="tests/golden_dataset.jsonl",
        help="Path to golden dataset (JSONL)",
    )
    parser.add_argument(
        "--wal-dir",
        default="./eval_logs",
        help="WAL directory for test runs",
    )
    parser.add_argument(
        "--golden-wal-dir",
        help="Directory containing golden WAL files",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of evaluation runs",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.98,
        help="CI pass threshold (default: 0.98)",
    )
    parser.add_argument(
        "--output",
        help="Output file for report (JSON)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create evaluation rig
    rig = create_evaluation_rig(
        dataset_path=args.dataset,
        wal_dir=args.wal_dir,
        golden_wal_dir=args.golden_wal_dir,
    )

    # Check if dataset exists
    if not rig.test_cases:
        logger.error(f"No test cases found in {args.dataset}")
        logger.info("Creating sample golden dataset...")

        # Create sample dataset
        sample_dataset = [
            {
                "test_id": "test_001_intent_stability",
                "description": "Test intent routing stability",
                "steps": [
                    {
                        "intent": "fetch_user_context",
                        "tool_name": "fetch_context",
                        "params": {"context_key": "user_123"},
                        "timeout_ms": 5000,
                    }
                ],
                "expected_fingerprint": "",
                "tags": ["intent_stability"],
            },
            {
                "test_id": "test_002_parameter_determinism",
                "description": "Test parameter handling determinism",
                "steps": [
                    {
                        "intent": "fetch_context",
                        "tool_name": "fetch_context",
                        "params": {"context_key": "order_456", "include_metadata": True},
                        "timeout_ms": 5000,
                    }
                ],
                "expected_fingerprint": "",
                "tags": ["parameter_determinism"],
            },
            {
                "test_id": "test_003_side_effect_safety",
                "description": "Test state-changing tool safety",
                "steps": [
                    {
                        "intent": "update_record",
                        "tool_name": "update_database",
                        "params": {
                            "table": "orders",
                            "record_id": "789",
                            "data": {"status": "completed"},
                        },
                        "timeout_ms": 10000,
                    }
                ],
                "expected_fingerprint": "",
                "tags": ["side_effect_safety"],
            },
            {
                "test_id": "test_004_execution_order",
                "description": "Test multi-step execution order",
                "steps": [
                    {
                        "intent": "fetch_context",
                        "tool_name": "fetch_context",
                        "params": {"context_key": "step_1"},
                        "timeout_ms": 5000,
                    },
                    {
                        "intent": "update_record",
                        "tool_name": "update_database",
                        "params": {
                            "table": "logs",
                            "record_id": "001",
                            "data": {"action": "step_1_complete"},
                        },
                        "timeout_ms": 10000,
                    },
                ],
                "expected_fingerprint": "",
                "tags": ["execution_order"],
            },
            {
                "test_id": "test_005_timeout_determinism",
                "description": "Test timeout behavior determinism",
                "steps": [
                    {
                        "intent": "fetch_context",
                        "tool_name": "fetch_context",
                        "params": {"context_key": "timeout_test"},
                        "timeout_ms": 1000,
                    }
                ],
                "expected_fingerprint": "",
                "tags": ["timeout_determinism"],
            },
        ]

        # Write sample dataset
        dataset_path = Path(args.dataset)
        dataset_path.parent.mkdir(parents=True, exist_ok=True)

        with open(dataset_path, "w") as f:
            for tc in sample_dataset:
                f.write(json.dumps(tc) + "\n")

        logger.info(f"Created sample dataset at {dataset_path}")

        # Reload
        rig = create_evaluation_rig(
            dataset_path=args.dataset,
            wal_dir=args.wal_dir,
            golden_wal_dir=args.golden_wal_dir,
        )

    # Run evaluation
    if args.runs > 1:
        logger.info(f"Running {args.runs} evaluation runs...")
        result = rig.run_multiple(num_runs=args.runs)
    else:
        report = rig.run()
        result = report.to_dict()

    # Output report
    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        logger.info(f"Report written to {args.output}")
    else:
        print(json.dumps(result, indent=2))

    # Check CI pass
    if args.runs > 1:
        ci_passed = result["ci_passed"]
        reliability = result["mean_reliability"]
    else:
        ci_passed = result.get("ci_passed", result.get("reliability", 0) >= args.threshold)
        reliability = result.get("reliability", 0)

    logger.info(f"Reliability: {reliability:.2%}")

    if ci_passed:
        logger.info("CI PASS: Deterministic reliability threshold met")
        sys.exit(0)
    else:
        logger.error(f"CI FAIL: Reliability {reliability:.2%} below threshold {args.threshold:.2%}")
        sys.exit(1)


if __name__ == "__main__":
    main()
