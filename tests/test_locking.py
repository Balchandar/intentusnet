"""
Tests for execution locking.
"""

import tempfile
import shutil
import os
import time

import pytest

from intentusnet.wal.locking import ExecutionLock


class TestExecutionLocking:
    """Test execution-level concurrency locking."""

    def setup_method(self):
        self.lock_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.lock_dir, ignore_errors=True)

    def test_acquire_and_release(self):
        """Test basic lock acquire and release."""
        lock = ExecutionLock(self.lock_dir, "exec-001")

        # Acquire
        lock.acquire()
        assert lock._fd is not None

        # Release
        lock.release()
        assert lock._fd is None

    def test_context_manager(self):
        """Test lock as context manager."""
        with ExecutionLock(self.lock_dir, "exec-002") as lock:
            assert lock._fd is not None

        # Lock should be released after context
        assert lock._fd is None

    def test_concurrent_lock_fails(self):
        """Test concurrent lock acquisition fails."""
        execution_id = "exec-003"

        # Acquire first lock
        lock1 = ExecutionLock(self.lock_dir, execution_id)
        lock1.acquire()

        # Attempt to acquire second lock (should fail)
        lock2 = ExecutionLock(self.lock_dir, execution_id)
        with pytest.raises(ValueError):
            lock2.acquire(timeout_sec=1)

        lock1.release()

    def test_stale_lock_cleanup(self):
        """Test stale lock detection and cleanup."""
        execution_id = "exec-004"

        # Create a stale lock (fake PID)
        lock1 = ExecutionLock(self.lock_dir, execution_id)
        lock1.acquire()

        # Manually corrupt lock to have non-existent PID
        lock_file = lock1.lock_file
        with open(lock_file, "w") as f:
            import json
            json.dump({
                "execution_id": execution_id,
                "pid": 999999,  # Non-existent PID
                "hostname": "localhost",
                "acquired_at": time.time() - 7200,  # 2 hours ago
            }, f)

        lock1.release()  # Close FD

        # New lock should detect stale lock and acquire
        lock2 = ExecutionLock(self.lock_dir, execution_id, stale_timeout_sec=3600)
        lock2.acquire()  # Should succeed
        lock2.release()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
