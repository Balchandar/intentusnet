"""
WAL Writer - Append-only, crash-safe writer.

Rules:
- All writes are fsynced before returning
- Hash chaining ensures integrity
- No overwrites allowed
- Thread-safe
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Optional

from intentusnet.utils.timestamps import now_iso

from .models import WALEntry, WALEntryType, ExecutionState


class WALWriter:
    """
    Append-only WAL writer with fsync guarantees.

    Thread-safe for concurrent execution recording.
    """

    def __init__(self, wal_dir: str, execution_id: str) -> None:
        self.wal_dir = Path(wal_dir)
        self.execution_id = execution_id
        self.wal_path = self.wal_dir / f"{execution_id}.wal"

        # Thread safety
        self._lock = threading.Lock()

        # Hash chaining
        self._last_hash: Optional[str] = None
        self._seq = 0

        # Ensure directory exists
        self.wal_dir.mkdir(parents=True, exist_ok=True)

        # File handle (opened in append mode)
        self._file = None

    def __enter__(self) -> WALWriter:
        self._file = open(self.wal_path, "a", encoding="utf-8")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._file:
            self._file.flush()
            os.fsync(self._file.fileno())
            self._file.close()
            self._file = None

    def append(self, entry_type: WALEntryType, payload: dict) -> WALEntry:
        """
        Append a WAL entry.

        Returns the written entry (with computed hash).
        Raises if write fails.
        """
        with self._lock:
            self._seq += 1

            entry = WALEntry(
                seq=self._seq,
                execution_id=self.execution_id,
                timestamp_iso=now_iso(),
                entry_type=entry_type,
                payload=payload,
                prev_hash=self._last_hash,
            )

            # Compute hash
            entry.entry_hash = entry.compute_hash()

            # Write to file (JSONL)
            if self._file is None:
                raise RuntimeError("WAL writer not opened (use context manager)")

            line = json.dumps(entry.to_dict(), ensure_ascii=False)
            self._file.write(line + "\n")
            self._file.flush()
            os.fsync(self._file.fileno())

            # Update chain
            self._last_hash = entry.entry_hash

            return entry

    def execution_started(self, envelope_hash: str, intent_name: str) -> WALEntry:
        """
        Write EXECUTION_STARTED entry.
        """
        return self.append(
            WALEntryType.EXECUTION_STARTED,
            {
                "execution_id": self.execution_id,
                "envelope_hash": envelope_hash,
                "intent_name": intent_name,
            },
        )

    def execution_completed(self, response_hash: str) -> WALEntry:
        """
        Write EXECUTION_COMPLETED entry.
        """
        return self.append(
            WALEntryType.EXECUTION_COMPLETED,
            {"execution_id": self.execution_id, "response_hash": response_hash},
        )

    def execution_failed(self, failure_type: str, reason: str, recoverable: bool) -> WALEntry:
        """
        Write EXECUTION_FAILED entry.
        """
        return self.append(
            WALEntryType.EXECUTION_FAILED,
            {
                "execution_id": self.execution_id,
                "failure_type": failure_type,
                "reason": reason,
                "recoverable": recoverable,
            },
        )

    def step_started(
        self,
        step_id: str,
        agent_name: str,
        side_effect: str,
        contracts: dict,
        input_hash: str,
    ) -> WALEntry:
        """
        Write STEP_STARTED entry (MUST be written BEFORE execution).
        """
        return self.append(
            WALEntryType.STEP_STARTED,
            {
                "step_id": step_id,
                "agent_name": agent_name,
                "side_effect": side_effect,
                "contracts": contracts,
                "input_hash": input_hash,
            },
        )

    def step_completed(self, step_id: str, output_hash: str, success: bool) -> WALEntry:
        """
        Write STEP_COMPLETED entry.
        """
        return self.append(
            WALEntryType.STEP_COMPLETED,
            {"step_id": step_id, "output_hash": output_hash, "success": success},
        )

    def step_failed(
        self, step_id: str, failure_type: str, reason: str, recoverable: bool
    ) -> WALEntry:
        """
        Write STEP_FAILED entry.
        """
        return self.append(
            WALEntryType.STEP_FAILED,
            {
                "step_id": step_id,
                "failure_type": failure_type,
                "reason": reason,
                "recoverable": recoverable,
            },
        )

    def fallback_triggered(self, from_agent: str, to_agent: str, reason: str) -> WALEntry:
        """
        Write FALLBACK_TRIGGERED entry (deterministic fallback decision).
        """
        return self.append(
            WALEntryType.FALLBACK_TRIGGERED,
            {"from_agent": from_agent, "to_agent": to_agent, "reason": reason},
        )

    def contract_validated(self, step_id: str, contracts: dict) -> WALEntry:
        """
        Write CONTRACT_VALIDATED entry.
        """
        return self.append(
            WALEntryType.CONTRACT_VALIDATED, {"step_id": step_id, "contracts": contracts}
        )

    def contract_violated(self, step_id: str, contract: str, reason: str) -> WALEntry:
        """
        Write CONTRACT_VIOLATED entry (execution must fail).
        """
        return self.append(
            WALEntryType.CONTRACT_VIOLATED,
            {"step_id": step_id, "contract": contract, "reason": reason},
        )

    def checkpoint(self, state: ExecutionState, completed_steps: list[str]) -> WALEntry:
        """
        Write CHECKPOINT entry (for recovery).
        """
        return self.append(
            WALEntryType.CHECKPOINT,
            {"state": state.value, "completed_steps": completed_steps},
        )
