"""
Tests for execution state machine.
"""

import tempfile
import shutil

import pytest

from intentusnet.wal import WALWriter, WALReader
from intentusnet.wal.state_manager import ExecutionStateManager, IllegalStateTransitionError
from intentusnet.wal.models import ExecutionState


class TestExecutionStateMachine:
    """Test execution state machine transitions."""

    def setup_method(self):
        self.wal_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.wal_dir, ignore_errors=True)

    def test_valid_transitions(self):
        """Test valid state transitions."""
        execution_id = "test-exec-001"

        with WALWriter(self.wal_dir, execution_id) as wal:
            state_mgr = ExecutionStateManager(wal, execution_id)

            # CREATED → STARTED
            state_mgr.initialize()
            assert state_mgr.current_state() == ExecutionState.CREATED

            state_mgr.transition(ExecutionState.STARTED)
            assert state_mgr.current_state() == ExecutionState.STARTED

            # STARTED → IN_PROGRESS
            state_mgr.transition(ExecutionState.IN_PROGRESS)
            assert state_mgr.current_state() == ExecutionState.IN_PROGRESS

            # IN_PROGRESS → COMPLETED
            state_mgr.transition(ExecutionState.COMPLETED)
            assert state_mgr.current_state() == ExecutionState.COMPLETED
            assert state_mgr.is_terminal()

    def test_illegal_transition(self):
        """Test illegal state transition raises error."""
        execution_id = "test-exec-002"

        with WALWriter(self.wal_dir, execution_id) as wal:
            state_mgr = ExecutionStateManager(wal, execution_id)
            state_mgr.initialize()
            state_mgr.transition(ExecutionState.STARTED)

            # STARTED → COMPLETED (illegal, must go through IN_PROGRESS)
            with pytest.raises(IllegalStateTransitionError):
                state_mgr.transition(ExecutionState.COMPLETED)

    def test_terminal_states(self):
        """Test terminal states."""
        assert ExecutionState.is_terminal(ExecutionState.COMPLETED)
        assert ExecutionState.is_terminal(ExecutionState.ABORTED)
        assert not ExecutionState.is_terminal(ExecutionState.IN_PROGRESS)

    def test_state_reconstruction(self):
        """Test state reconstruction from WAL."""
        execution_id = "test-exec-003"

        # Create execution and transition states
        with WALWriter(self.wal_dir, execution_id) as wal:
            state_mgr = ExecutionStateManager(wal, execution_id)
            state_mgr.initialize()
            state_mgr.transition(ExecutionState.STARTED)
            state_mgr.transition(ExecutionState.IN_PROGRESS)

        # Reconstruct state from WAL
        reader = WALReader(self.wal_dir, execution_id)
        reconstructed_state = ExecutionStateManager.reconstruct_state(reader)

        assert reconstructed_state == ExecutionState.IN_PROGRESS

    def test_recovery_path(self):
        """Test recovery state transitions."""
        execution_id = "test-exec-004"

        with WALWriter(self.wal_dir, execution_id) as wal:
            state_mgr = ExecutionStateManager(wal, execution_id)
            state_mgr.initialize()
            state_mgr.transition(ExecutionState.STARTED)
            state_mgr.transition(ExecutionState.IN_PROGRESS)

            # IN_PROGRESS → FAILED
            state_mgr.transition(ExecutionState.FAILED)
            assert state_mgr.current_state() == ExecutionState.FAILED

            # FAILED → RECOVERING
            state_mgr.transition(ExecutionState.RECOVERING)
            assert state_mgr.current_state() == ExecutionState.RECOVERING

            # RECOVERING → IN_PROGRESS
            state_mgr.transition(ExecutionState.IN_PROGRESS)
            assert state_mgr.current_state() == ExecutionState.IN_PROGRESS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
