"""
Execution State Manager - Production state machine enforcement.

Manages execution lifecycle with strict state transition validation.
"""

from __future__ import annotations

import logging
from typing import Optional

from .models import ExecutionState, WALEntryType
from .writer import WALWriter
from .reader import WALReader

logger = logging.getLogger("intentusnet.execution.state")


class IllegalStateTransitionError(Exception):
    """Raised when illegal state transition is attempted."""
    pass


class ExecutionStateManager:
    """
    Enforces execution state machine.

    All state transitions are validated and persisted in WAL.
    """

    def __init__(self, wal_writer: WALWriter, execution_id: str) -> None:
        self.wal_writer = wal_writer
        self.execution_id = execution_id
        self._current_state: Optional[ExecutionState] = None

    def initialize(self) -> None:
        """
        Initialize execution (CREATED state).
        """
        self._current_state = ExecutionState.CREATED
        self.wal_writer.append(
            WALEntryType.EXECUTION_CREATED,
            {
                "execution_id": self.execution_id,
                "state": ExecutionState.CREATED.value,
            },
        )

    def transition(self, to_state: ExecutionState, reason: Optional[str] = None) -> None:
        """
        Transition to new state.

        Raises IllegalStateTransitionError if transition is not legal.
        """
        if self._current_state is None:
            raise IllegalStateTransitionError(
                f"Cannot transition to {to_state.value}: execution not initialized"
            )

        # Validate transition
        if not ExecutionState.validate_transition(self._current_state, to_state):
            raise IllegalStateTransitionError(
                f"Illegal state transition: {self._current_state.value} → {to_state.value}"
            )

        # Persist transition in WAL
        self.wal_writer.append(
            WALEntryType.EXECUTION_STATE_TRANSITION,
            {
                "execution_id": self.execution_id,
                "from_state": self._current_state.value,
                "to_state": to_state.value,
                "reason": reason,
            },
        )

        logger.info(f"State transition: {self._current_state.value} → {to_state.value}")
        self._current_state = to_state

    def current_state(self) -> Optional[ExecutionState]:
        """Get current state."""
        return self._current_state

    def is_terminal(self) -> bool:
        """Check if execution is in terminal state."""
        if self._current_state is None:
            return False
        return ExecutionState.is_terminal(self._current_state)

    @classmethod
    def reconstruct_state(cls, wal_reader: WALReader) -> Optional[ExecutionState]:
        """
        Reconstruct current state from WAL.
        """
        entries = wal_reader.read_all(verify_integrity=True)
        if not entries:
            return None

        current_state = None

        for entry in entries:
            if entry.entry_type == WALEntryType.EXECUTION_CREATED:
                current_state = ExecutionState.CREATED
            elif entry.entry_type == WALEntryType.EXECUTION_STATE_TRANSITION:
                to_state = ExecutionState(entry.payload.get("to_state"))
                current_state = to_state
            elif entry.entry_type == WALEntryType.EXECUTION_STARTED:
                # Legacy support
                current_state = ExecutionState.STARTED
            elif entry.entry_type == WALEntryType.EXECUTION_COMPLETED:
                current_state = ExecutionState.COMPLETED
            elif entry.entry_type == WALEntryType.EXECUTION_FAILED:
                current_state = ExecutionState.FAILED
            elif entry.entry_type == WALEntryType.EXECUTION_ABORTED:
                current_state = ExecutionState.ABORTED

        return current_state
