"""
Tests for structured failures.
"""

import tempfile
import shutil
from pathlib import Path

import pytest

from intentusnet.failures import (
    FailureType,
    StructuredFailure,
    RecoveryStrategy,
    FailureRegistry,
)


class TestStructuredFailures:
    """
    Test structured failure system.
    """

    def test_failure_creation(self):
        """
        Test creating a structured failure.
        """
        failure = StructuredFailure(
            failure_type=FailureType.TIMEOUT,
            execution_id="exec-001",
            step_id="step-1",
            agent_name="agent-1",
            reason="Execution timeout",
            details={"timeout_ms": 1000, "elapsed_ms": 1500},
            recoverable=True,
            recovery_strategy=RecoveryStrategy.RETRY,
        )

        assert failure.failure_type == FailureType.TIMEOUT
        assert failure.recoverable is True
        assert failure.recovery_strategy == RecoveryStrategy.RETRY

    def test_failure_serialization(self):
        """
        Test failure serialization/deserialization.
        """
        failure = StructuredFailure(
            failure_type=FailureType.CONTRACT_VIOLATION,
            execution_id="exec-002",
            reason="Contract violated",
            details={"contract": "exactly_once"},
            recoverable=False,
            recovery_strategy=RecoveryStrategy.ABORT,
        )

        # Serialize
        data = failure.to_dict()

        # Deserialize
        failure2 = StructuredFailure.from_dict(data)

        assert failure2.failure_type == failure.failure_type
        assert failure2.execution_id == failure.execution_id
        assert failure2.reason == failure.reason
        assert failure2.recoverable == failure.recoverable

    def test_failure_causality(self):
        """
        Test failure causality chain.
        """
        root_cause = StructuredFailure(
            failure_type=FailureType.NETWORK_ERROR,
            execution_id="exec-003",
            reason="Network timeout",
            recoverable=True,
        )

        caused_failure = StructuredFailure(
            failure_type=FailureType.AGENT_UNAVAILABLE,
            execution_id="exec-003",
            reason="Agent unreachable",
            recoverable=True,
            caused_by=root_cause,
        )

        assert caused_failure.caused_by is not None
        assert caused_failure.caused_by.failure_type == FailureType.NETWORK_ERROR


class TestFailureRegistry:
    """
    Test failure registry.
    """

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_record_and_query(self):
        """
        Test recording and querying failures.
        """
        registry = FailureRegistry("exec-001")

        failure1 = StructuredFailure(
            failure_type=FailureType.TIMEOUT,
            execution_id="exec-001",
            step_id="step1",
            reason="Timeout",
            recoverable=True,
        )

        failure2 = StructuredFailure(
            failure_type=FailureType.CONTRACT_VIOLATION,
            execution_id="exec-001",
            step_id="step2",
            reason="Contract violated",
            recoverable=False,
        )

        registry.record(failure1)
        registry.record(failure2)

        # Query by type
        timeouts = registry.get_by_type(FailureType.TIMEOUT)
        assert len(timeouts) == 1

        # Query by step
        step1_failures = registry.get_by_step("step1")
        assert len(step1_failures) == 1

        # Query recoverable
        recoverable = registry.get_recoverable()
        assert len(recoverable) == 1

        # Query non-recoverable
        non_recoverable = registry.get_non_recoverable()
        assert len(non_recoverable) == 1

    def test_save_and_load(self):
        """
        Test saving and loading failure registry.
        """
        registry = FailureRegistry("exec-002")

        failure = StructuredFailure(
            failure_type=FailureType.AGENT_ERROR,
            execution_id="exec-002",
            reason="Agent crashed",
            recoverable=False,
        )

        registry.record(failure)

        # Save
        path = Path(self.tmp_dir) / "failures.json"
        registry.save(path)

        # Load
        registry2 = FailureRegistry.load(path)

        assert registry2.execution_id == "exec-002"
        assert len(registry2.get_all()) == 1
        assert registry2.get_all()[0].failure_type == FailureType.AGENT_ERROR


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
