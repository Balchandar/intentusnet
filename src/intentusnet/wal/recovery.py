"""
Crash Recovery Manager - kill -9 safe recovery.

Rules:
- Scans WAL on startup
- Detects incomplete executions
- Deterministically resumes OR fails explicitly
- Never re-executes irreversible steps
- All recovery actions are WAL-recorded
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .models import ExecutionState, WALEntryType
from .reader import WALReader
from .writer import WALWriter

logger = logging.getLogger("intentusnet.wal.recovery")


@dataclass
class RecoveryDecision:
    """
    Deterministic recovery decision.
    """

    execution_id: str
    can_resume: bool
    reason: str
    state: ExecutionState
    completed_steps: list[str]
    irreversible_steps_executed: list[str]


class RecoveryError(Exception):
    """
    Raised when recovery cannot proceed.
    """

    pass


class RecoveryManager:
    """
    Manages crash recovery for incomplete executions.

    Recovery is deterministic and conservative:
    - If state is ambiguous → FAIL
    - If irreversible step may have executed → FAIL
    - If recovery is safe → RESUME
    """

    def __init__(self, wal_dir: str) -> None:
        self.wal_dir = Path(wal_dir)

    def scan_incomplete_executions(self) -> list[str]:
        """
        Scan WAL directory for incomplete executions.

        Returns list of execution IDs that may need recovery.
        """
        if not self.wal_dir.exists():
            return []

        incomplete = []
        for wal_file in self.wal_dir.glob("*.wal"):
            execution_id = wal_file.stem
            reader = WALReader(str(self.wal_dir), execution_id)

            try:
                entries = reader.read_all(verify_integrity=True)
                if not entries:
                    continue

                # Check terminal state
                last_entry = entries[-1]
                if last_entry.entry_type not in [
                    WALEntryType.EXECUTION_COMPLETED,
                    WALEntryType.EXECUTION_FAILED,
                    WALEntryType.EXECUTION_ABORTED,
                ]:
                    incomplete.append(execution_id)

            except Exception as e:
                logger.warning(f"Failed to read WAL for {execution_id}: {e}")
                incomplete.append(execution_id)

        return incomplete

    def analyze_execution(self, execution_id: str) -> RecoveryDecision:
        """
        Analyze an incomplete execution and determine recovery action.

        Returns RecoveryDecision with:
        - can_resume: True if safe to resume
        - reason: Explanation of decision
        - state: Current execution state
        - completed_steps: Steps that completed successfully
        - irreversible_steps_executed: Irreversible steps that ran
        """
        reader = WALReader(str(self.wal_dir), execution_id)

        if not reader.exists():
            raise RecoveryError(f"WAL not found for execution {execution_id}")

        # Read and verify integrity
        try:
            entries = reader.read_all(verify_integrity=True)
        except Exception as e:
            return RecoveryDecision(
                execution_id=execution_id,
                can_resume=False,
                reason=f"WAL integrity check failed: {e}",
                state=ExecutionState.FAILED,
                completed_steps=[],
                irreversible_steps_executed=[],
            )

        if not entries:
            return RecoveryDecision(
                execution_id=execution_id,
                can_resume=False,
                reason="Empty WAL",
                state=ExecutionState.FAILED,
                completed_steps=[],
                irreversible_steps_executed=[],
            )

        # Analyze state
        state = ExecutionState.STARTED
        completed_steps = []
        irreversible_steps = []
        pending_steps = {}  # step_id -> WALEntry (STEP_STARTED)

        for entry in entries:
            if entry.entry_type == WALEntryType.EXECUTION_STARTED:
                state = ExecutionState.IN_PROGRESS

            elif entry.entry_type == WALEntryType.EXECUTION_COMPLETED:
                state = ExecutionState.COMPLETED

            elif entry.entry_type == WALEntryType.EXECUTION_FAILED:
                state = ExecutionState.FAILED

            elif entry.entry_type == WALEntryType.STEP_STARTED:
                step_id = entry.payload.get("step_id")
                if step_id:
                    pending_steps[step_id] = entry

            elif entry.entry_type == WALEntryType.STEP_COMPLETED:
                step_id = entry.payload.get("step_id")
                if step_id:
                    completed_steps.append(step_id)
                    # Check if irreversible
                    if step_id in pending_steps:
                        started_entry = pending_steps[step_id]
                        side_effect = started_entry.payload.get("side_effect", "")
                        if side_effect == "irreversible":
                            irreversible_steps.append(step_id)
                    pending_steps.pop(step_id, None)

            elif entry.entry_type == WALEntryType.STEP_FAILED:
                step_id = entry.payload.get("step_id")
                if step_id:
                    pending_steps.pop(step_id, None)

        # Determine if recovery is safe
        can_resume = True
        reason = "Execution can be safely resumed"

        # Terminal states - no recovery needed
        if state in [ExecutionState.COMPLETED, ExecutionState.FAILED]:
            can_resume = False
            reason = f"Execution already in terminal state: {state.value}"

        # Check for ambiguous irreversible steps
        elif pending_steps:
            # Steps that started but didn't complete
            for step_id, started_entry in pending_steps.items():
                side_effect = started_entry.payload.get("side_effect", "")
                if side_effect == "irreversible":
                    can_resume = False
                    reason = (
                        f"Cannot resume: irreversible step '{step_id}' started but not completed. "
                        f"State is ambiguous - side effect may have occurred."
                    )
                    break

        return RecoveryDecision(
            execution_id=execution_id,
            can_resume=can_resume,
            reason=reason,
            state=state,
            completed_steps=completed_steps,
            irreversible_steps_executed=irreversible_steps,
        )

    def abort_execution(self, execution_id: str, reason: str) -> None:
        """
        Mark an execution as aborted (cannot recover).

        Appends EXECUTION_ABORTED to WAL.
        """
        with WALWriter(str(self.wal_dir), execution_id) as writer:
            # Reload sequence from existing WAL
            reader = WALReader(str(self.wal_dir), execution_id)
            entries = reader.read_all(verify_integrity=False)
            if entries:
                writer._seq = entries[-1].seq
                writer._last_hash = entries[-1].entry_hash

            writer.append(
                WALEntryType.EXECUTION_ABORTED,
                {"reason": reason, "aborted_by": "recovery_manager"},
            )

        logger.info(f"Execution {execution_id} aborted: {reason}")

    def resume_execution(self, execution_id: str) -> RecoveryDecision:
        """
        Attempt to resume an incomplete execution.

        Returns RecoveryDecision.
        Raises RecoveryError if resume is not safe.
        """
        decision = self.analyze_execution(execution_id)

        if not decision.can_resume:
            raise RecoveryError(
                f"Cannot resume execution {execution_id}: {decision.reason}"
            )

        # Record recovery start
        with WALWriter(str(self.wal_dir), execution_id) as writer:
            # Reload sequence
            reader = WALReader(str(self.wal_dir), execution_id)
            entries = reader.read_all(verify_integrity=True)
            if entries:
                writer._seq = entries[-1].seq
                writer._last_hash = entries[-1].entry_hash

            writer.append(
                WALEntryType.RECOVERY_STARTED,
                {
                    "completed_steps": decision.completed_steps,
                    "state": decision.state.value,
                },
            )

        logger.info(f"Resuming execution {execution_id}: {decision.reason}")
        return decision
