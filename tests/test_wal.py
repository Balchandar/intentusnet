"""
Tests for Write-Ahead Log (WAL).
"""

import tempfile
import shutil
from pathlib import Path

import pytest

from intentusnet.wal import (
    WALWriter,
    WALReader,
    WALEntryType,
    ExecutionState,
    RecoveryManager,
)
from intentusnet.wal.reader import WALIntegrityError


class TestWAL:
    """
    Test WAL write, read, and integrity verification.
    """

    def setup_method(self):
        """
        Create temporary WAL directory.
        """
        self.wal_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """
        Clean up temporary directory.
        """
        shutil.rmtree(self.wal_dir, ignore_errors=True)

    def test_write_and_read(self):
        """
        Test basic WAL write and read.
        """
        execution_id = "test-exec-001"

        # Write entries
        with WALWriter(self.wal_dir, execution_id) as wal:
            entry1 = wal.execution_started("hash123", "test_intent")
            entry2 = wal.step_started(
                "step1", "agent1", "read_only", {"exactly_once": False}, "input_hash_1"
            )
            entry3 = wal.step_completed("step1", "output_hash_1", True)
            entry4 = wal.execution_completed("response_hash")

        # Read entries
        reader = WALReader(self.wal_dir, execution_id)
        entries = reader.read_all(verify_integrity=True)

        assert len(entries) == 4
        assert entries[0].entry_type == WALEntryType.EXECUTION_STARTED
        assert entries[1].entry_type == WALEntryType.STEP_STARTED
        assert entries[2].entry_type == WALEntryType.STEP_COMPLETED
        assert entries[3].entry_type == WALEntryType.EXECUTION_COMPLETED

    def test_hash_chain_integrity(self):
        """
        Test hash chain integrity verification.
        """
        execution_id = "test-exec-002"

        # Write entries
        with WALWriter(self.wal_dir, execution_id) as wal:
            wal.execution_started("hash123", "test_intent")
            wal.step_started("step1", "agent1", "read_only", {}, "input_hash_1")

        # Read and verify
        reader = WALReader(self.wal_dir, execution_id)
        entries = reader.read_all(verify_integrity=True)

        # Verify hash chain
        assert entries[0].prev_hash is None
        assert entries[1].prev_hash == entries[0].entry_hash

    def test_corrupted_wal_detection(self):
        """
        Test detection of corrupted WAL.
        """
        execution_id = "test-exec-003"

        # Write entries
        with WALWriter(self.wal_dir, execution_id) as wal:
            wal.execution_started("hash123", "test_intent")
            wal.step_started("step1", "agent1", "read_only", {}, "input_hash_1")

        # Corrupt WAL by modifying file
        wal_path = Path(self.wal_dir) / f"{execution_id}.wal"
        with open(wal_path, "a") as f:
            f.write('{"corrupted": true}\n')

        # Read should fail integrity check
        reader = WALReader(self.wal_dir, execution_id)
        with pytest.raises(WALIntegrityError):
            reader.read_all(verify_integrity=True)


class TestRecovery:
    """
    Test crash recovery.
    """

    def setup_method(self):
        self.wal_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.wal_dir, ignore_errors=True)

    def test_scan_incomplete_executions(self):
        """
        Test scanning for incomplete executions.
        """
        # Write complete execution
        with WALWriter(self.wal_dir, "complete-exec") as wal:
            wal.execution_started("hash1", "intent1")
            wal.execution_completed("response_hash")

        # Write incomplete execution
        with WALWriter(self.wal_dir, "incomplete-exec") as wal:
            wal.execution_started("hash2", "intent2")
            wal.step_started("step1", "agent1", "read_only", {}, "input_hash")

        # Scan
        recovery_mgr = RecoveryManager(self.wal_dir)
        incomplete = recovery_mgr.scan_incomplete_executions()

        assert "incomplete-exec" in incomplete
        assert "complete-exec" not in incomplete

    def test_recovery_decision_safe(self):
        """
        Test recovery decision for safe (read_only) execution.
        """
        execution_id = "safe-exec"

        # Write incomplete safe execution
        with WALWriter(self.wal_dir, execution_id) as wal:
            wal.execution_started("hash1", "intent1")
            wal.step_started("step1", "agent1", "read_only", {}, "input_hash")
            # Step NOT completed - but side effect is read_only

        # Analyze
        recovery_mgr = RecoveryManager(self.wal_dir)
        decision = recovery_mgr.analyze_execution(execution_id)

        assert decision.can_resume is True
        assert decision.state == ExecutionState.IN_PROGRESS

    def test_recovery_decision_unsafe_irreversible(self):
        """
        Test recovery decision for unsafe (irreversible) execution.
        """
        execution_id = "unsafe-exec"

        # Write incomplete irreversible execution
        with WALWriter(self.wal_dir, execution_id) as wal:
            wal.execution_started("hash1", "intent1")
            wal.step_started("step1", "agent1", "irreversible", {}, "input_hash")
            # Step NOT completed - and side effect is irreversible

        # Analyze
        recovery_mgr = RecoveryManager(self.wal_dir)
        decision = recovery_mgr.analyze_execution(execution_id)

        assert decision.can_resume is False
        assert "irreversible" in decision.reason.lower()

    def test_abort_execution(self):
        """
        Test aborting an execution.
        """
        execution_id = "abort-exec"

        # Write incomplete execution
        with WALWriter(self.wal_dir, execution_id) as wal:
            wal.execution_started("hash1", "intent1")

        # Abort
        recovery_mgr = RecoveryManager(self.wal_dir)
        recovery_mgr.abort_execution(execution_id, "Manual abort")

        # Verify aborted
        reader = WALReader(self.wal_dir, execution_id)
        entries = reader.read_all(verify_integrity=True)

        last_entry = entries[-1]
        assert last_entry.entry_type == WALEntryType.EXECUTION_ABORTED
        assert "Manual abort" in last_entry.payload["reason"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
