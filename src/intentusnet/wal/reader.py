"""
WAL Reader - Read and verify WAL integrity.

Rules:
- Verifies hash chain integrity
- Detects truncation or corruption
- Returns entries in sequential order
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Optional

from .models import WALEntry, ExecutionState, ExecutionCheckpoint


class WALIntegrityError(Exception):
    """
    Raised when WAL integrity check fails.
    """

    pass


class WALReader:
    """
    Read and verify WAL files.
    """

    def __init__(self, wal_dir: str, execution_id: str) -> None:
        self.wal_dir = Path(wal_dir)
        self.execution_id = execution_id
        self.wal_path = self.wal_dir / f"{execution_id}.wal"

    def exists(self) -> bool:
        """
        Check if WAL file exists.
        """
        return self.wal_path.exists()

    def read_all(self, verify_integrity: bool = True) -> list[WALEntry]:
        """
        Read all WAL entries.

        If verify_integrity=True, validates hash chain.
        Raises WALIntegrityError if chain is broken.
        """
        entries = list(self.iter_entries())

        if verify_integrity:
            self._verify_chain(entries)

        return entries

    def iter_entries(self) -> Iterator[WALEntry]:
        """
        Iterate over WAL entries (streaming).
        """
        if not self.wal_path.exists():
            return

        with open(self.wal_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    entry = WALEntry.from_dict(data)
                    yield entry
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    raise WALIntegrityError(f"Corrupted WAL entry: {e}") from e

    def get_checkpoint(self) -> Optional[ExecutionCheckpoint]:
        """
        Get the most recent checkpoint (for recovery).
        """
        entries = self.read_all(verify_integrity=True)
        if not entries:
            return None

        # Find last checkpoint
        checkpoint_entry = None
        for entry in reversed(entries):
            if entry.entry_type.value == "checkpoint":
                checkpoint_entry = entry
                break

        if checkpoint_entry is None:
            # No checkpoint - reconstruct from WAL
            return self._reconstruct_checkpoint(entries)

        # Parse checkpoint
        payload = checkpoint_entry.payload
        return ExecutionCheckpoint(
            execution_id=self.execution_id,
            state=ExecutionState(payload["state"]),
            last_wal_seq=checkpoint_entry.seq,
            last_wal_hash=checkpoint_entry.entry_hash or "",
            completed_steps=payload.get("completed_steps", []),
            pending_steps=[],
            metadata={},
        )

    def _reconstruct_checkpoint(self, entries: list[WALEntry]) -> ExecutionCheckpoint:
        """
        Reconstruct checkpoint from WAL entries (no explicit checkpoint found).
        """
        if not entries:
            raise WALIntegrityError("Cannot reconstruct checkpoint from empty WAL")

        state = ExecutionState.STARTED
        completed_steps = []

        for entry in entries:
            if entry.entry_type.value == "execution.started":
                state = ExecutionState.IN_PROGRESS
            elif entry.entry_type.value == "execution.completed":
                state = ExecutionState.COMPLETED
            elif entry.entry_type.value == "execution.failed":
                state = ExecutionState.FAILED
            elif entry.entry_type.value == "step.completed":
                step_id = entry.payload.get("step_id")
                if step_id:
                    completed_steps.append(step_id)

        last_entry = entries[-1]
        return ExecutionCheckpoint(
            execution_id=self.execution_id,
            state=state,
            last_wal_seq=last_entry.seq,
            last_wal_hash=last_entry.entry_hash or "",
            completed_steps=completed_steps,
            pending_steps=[],
            metadata={},
        )

    def _verify_chain(self, entries: list[WALEntry]) -> None:
        """
        Verify hash chain integrity.

        Raises WALIntegrityError if chain is broken.
        """
        if not entries:
            return

        prev_hash = None
        for i, entry in enumerate(entries):
            # Check sequence monotonicity
            if entry.seq != i + 1:
                raise WALIntegrityError(
                    f"Sequence mismatch at index {i}: expected {i + 1}, got {entry.seq}"
                )

            # Check hash chain
            if entry.prev_hash != prev_hash:
                raise WALIntegrityError(
                    f"Hash chain broken at seq={entry.seq}: "
                    f"expected prev_hash={prev_hash}, got {entry.prev_hash}"
                )

            # Verify entry hash
            computed_hash = entry.compute_hash()
            if entry.entry_hash != computed_hash:
                raise WALIntegrityError(
                    f"Hash mismatch at seq={entry.seq}: "
                    f"expected {computed_hash}, got {entry.entry_hash}"
                )

            prev_hash = entry.entry_hash
