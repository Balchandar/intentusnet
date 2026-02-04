"""
WAL Writer - Append-only, crash-safe writer.

Phase I Durability Boundary Definition
======================================

The IntentusNet durability guarantee begins at the WAL COMMIT BOUNDARY:

    EXECUTION_STARTED written to WAL
    +
    fsync() returns successfully
    =
    COMMIT BOUNDARY (durability begins here)

BEFORE the commit boundary:
- Message loss IS possible
- Caller may receive connection error, timeout, or no response
- This is "pre-WAL loss" and is EXPECTED under chaos conditions
- IntentusNet provides AT-MOST-ONCE delivery in this zone

AFTER the commit boundary:
- Message loss requires WAL corruption
- WAL corruption IS DETECTABLE via hash chain verification
- Recovery can identify and resume the execution
- This is the "durable zone"

See: docs/phase-i-remediation-plan.md Section 5

Rules:
- All writes are fsynced before returning (CRITICAL for durability guarantee)
- Hash chaining ensures integrity (detects tampering, corruption)
- No overwrites allowed (append-only)
- Thread-safe (concurrent recording supported)
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Optional

from intentusnet.utils.timestamps import now_iso

from .models import WALEntry, WALEntryType, ExecutionState, WALSigner, WALSignatureError


class WALSigningError(RuntimeError):
    """Raised when WAL signing fails or is required but not configured."""
    pass


class WALWriter:
    """
    Append-only WAL writer with fsync guarantees.

    Thread-safe for concurrent execution recording.

    Phase I REGULATED mode:
    - If signer is provided, ALL entries are signed with Ed25519
    - If require_signing=True and no signer, raises WALSigningError
    - Signatures are stored in each WAL entry
    """

    def __init__(
        self,
        wal_dir: str,
        execution_id: str,
        *,
        signer: Optional[WALSigner] = None,
        require_signing: bool = False,
    ) -> None:
        """
        Initialize WAL writer.

        Args:
            wal_dir: Directory to store WAL files
            execution_id: Unique execution identifier
            signer: Optional WALSigner for entry signing (Phase I REGULATED)
            require_signing: If True, fail if signer is not provided

        Raises:
            WALSigningError: If require_signing=True but signer is None
        """
        # Phase I REGULATED: Enforce signing requirement
        if require_signing and signer is None:
            raise WALSigningError(
                "WAL signing is required but no signer provided. "
                "For REGULATED compliance, provide an Ed25519WALSigner. "
                "See: docs/phase-i-remediation-plan.md Section 6"
            )

        self.wal_dir = Path(wal_dir)
        self.execution_id = execution_id
        self.wal_path = self.wal_dir / f"{execution_id}.wal"

        # Signing (Phase I REGULATED)
        self._signer = signer
        self._require_signing = require_signing

        # Thread safety
        self._lock = threading.Lock()

        # Hash chaining
        self._last_hash: Optional[str] = None
        self._seq = 0

        # Ensure directory exists
        self.wal_dir.mkdir(parents=True, exist_ok=True)

        # File handle (opened in append mode)
        self._file = None

    @property
    def is_signing_enabled(self) -> bool:
        """Check if WAL signing is enabled."""
        return self._signer is not None

    @property
    def signer_key_id(self) -> Optional[str]:
        """Get the key ID of the signer, or None if signing disabled."""
        return self._signer.key_id if self._signer else None

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

            # Sign entry if signer is configured (Phase I REGULATED)
            if self._signer is not None:
                entry.sign(self._signer)

            # Write to file (JSONL)
            if self._file is None:
                raise RuntimeError("WAL writer not opened (use context manager)")

            line = json.dumps(entry.to_dict(), ensure_ascii=False)
            self._file.write(line + "\n")
            self._file.flush()

            # ============================================================
            # DURABILITY BOUNDARY: fsync() is the commit point.
            # After fsync returns, the entry is durable.
            # Before fsync returns, crash = entry may be lost.
            # This is the ONLY point where durability is established.
            # ============================================================
            os.fsync(self._file.fileno())

            # Update chain (only after successful fsync)
            self._last_hash = entry.entry_hash

            # Post-condition: Entry is now durable
            assert self._last_hash == entry.entry_hash, "Hash chain inconsistency"

            return entry

    def execution_started(
        self,
        envelope_hash: str,
        intent_name: str,
        *,
        config_hash: str = None,
        require_determinism: bool = True,
    ) -> WALEntry:
        """
        Write EXECUTION_STARTED entry.

        ============================================================
        THIS IS THE DURABILITY COMMIT BOUNDARY.
        ============================================================

        Once this method returns successfully:
        - The execution IS durable (survives crash)
        - Loss requires WAL corruption (detectable)
        - Recovery can identify this execution

        Before this method returns:
        - The execution is NOT durable
        - Process crash = message lost (pre-WAL loss)
        - Caller may or may not receive error

        Args:
            envelope_hash: SHA256 hash of the intent envelope
            intent_name: Name of the intent being executed
            config_hash: Hash of router configuration (for drift detection)
            require_determinism: Whether determinism mode is enabled
        """
        payload = {
            "execution_id": self.execution_id,
            "envelope_hash": envelope_hash,
            "intent_name": intent_name,
        }

        # Phase I: Include config hash for drift detection
        if config_hash is not None:
            payload["config_hash"] = config_hash
            payload["require_determinism"] = require_determinism

        return self.append(WALEntryType.EXECUTION_STARTED, payload)

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
