"""
Tests for WAL ↔ Record consistency.
"""

import tempfile
import shutil

import pytest

from intentusnet.wal import WALWriter
from intentusnet.recording.store import FileExecutionStore
from intentusnet.recording.models import ExecutionRecord, ExecutionHeader
from intentusnet.recording.consistency import ConsistencyChecker
from intentusnet.utils.timestamps import now_iso


class TestConsistency:
    """Test WAL ↔ Record consistency checking."""

    def setup_method(self):
        self.wal_dir = tempfile.mkdtemp()
        self.record_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.wal_dir, ignore_errors=True)
        shutil.rmtree(self.record_dir, ignore_errors=True)

    def test_consistent_execution(self):
        """Test WAL and Record are consistent."""
        execution_id = "test-exec-001"
        envelope_hash = "abc123"

        # Write WAL
        with WALWriter(self.wal_dir, execution_id) as wal:
            wal.execution_started(envelope_hash, "test_intent")
            wal.step_started("step1", "agent1", "read_only", {}, "input_hash")
            wal.step_completed("step1", "output_hash", True)
            wal.execution_completed("response_hash")

        # Create matching record
        record = ExecutionRecord.new(
            execution_id=execution_id,
            created_utc_iso=now_iso(),
            env={"intent": {"name": "test_intent"}},
        )
        record.header.envelopeHash = envelope_hash

        store = FileExecutionStore(self.record_dir)
        store.save(record)

        # Check consistency
        checker = ConsistencyChecker(self.wal_dir, store)
        violations = checker.check(execution_id)

        assert len(violations) == 0

    def test_envelope_hash_mismatch(self):
        """Test envelope hash mismatch is detected."""
        execution_id = "test-exec-002"

        # Write WAL with one hash
        with WALWriter(self.wal_dir, execution_id) as wal:
            wal.execution_started("hash_abc", "test_intent")

        # Create record with different hash
        record = ExecutionRecord.new(
            execution_id=execution_id,
            created_utc_iso=now_iso(),
            env={"intent": {"name": "test_intent"}},
        )
        record.header.envelopeHash = "hash_xyz"  # Different!

        store = FileExecutionStore(self.record_dir)
        store.save(record)

        # Check consistency
        checker = ConsistencyChecker(self.wal_dir, store)
        violations = checker.check(execution_id)

        assert len(violations) > 0
        assert any(v.violation_type == "envelope_hash_mismatch" for v in violations)

    def test_missing_wal(self):
        """Test missing WAL is detected."""
        execution_id = "test-exec-003"

        # Create record without WAL
        record = ExecutionRecord.new(
            execution_id=execution_id,
            created_utc_iso=now_iso(),
            env={},
        )

        store = FileExecutionStore(self.record_dir)
        store.save(record)

        # Check consistency
        checker = ConsistencyChecker(self.wal_dir, store)
        violations = checker.check(execution_id)

        assert len(violations) > 0
        assert any(v.violation_type == "wal_missing" for v in violations)

    def test_missing_record(self):
        """Test missing record is detected."""
        execution_id = "test-exec-004"

        # Write WAL without record
        with WALWriter(self.wal_dir, execution_id) as wal:
            wal.execution_started("hash", "test_intent")

        store = FileExecutionStore(self.record_dir)

        # Check consistency
        checker = ConsistencyChecker(self.wal_dir, store)
        violations = checker.check(execution_id)

        assert len(violations) > 0
        assert any(v.violation_type == "record_missing" for v in violations)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
