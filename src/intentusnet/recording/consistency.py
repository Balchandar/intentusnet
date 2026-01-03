"""
WAL ↔ Record consistency enforcement.

Verifies that WAL and Records are consistent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
import logging

from intentusnet.wal.reader import WALReader
from intentusnet.wal.models import WALEntryType
from .store import ExecutionStore
from .models import ExecutionRecord

logger = logging.getLogger("intentusnet.consistency")


@dataclass
class ConsistencyViolation:
    """WAL ↔ Record consistency violation."""
    execution_id: str
    violation_type: str
    description: str
    details: dict

    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "violation_type": self.violation_type,
            "description": self.description,
            "details": self.details,
        }


class ConsistencyChecker:
    """
    Verifies WAL ↔ Record consistency.

    Ensures:
    - Every completed WAL step has corresponding record entry
    - Record hashes match WAL hashes
    - No orphaned records or WAL entries
    """

    def __init__(self, wal_dir: str, record_store: ExecutionStore) -> None:
        self.wal_dir = wal_dir
        self.record_store = record_store

    def check(self, execution_id: str) -> List[ConsistencyViolation]:
        """
        Check consistency for execution.

        Returns list of violations (empty if consistent).
        """
        violations: List[ConsistencyViolation] = []

        # Read WAL
        wal_reader = WALReader(self.wal_dir, execution_id)
        if not wal_reader.exists():
            violations.append(
                ConsistencyViolation(
                    execution_id=execution_id,
                    violation_type="wal_missing",
                    description="WAL file does not exist",
                    details={},
                )
            )
            return violations

        try:
            wal_entries = wal_reader.read_all(verify_integrity=True)
        except Exception as e:
            violations.append(
                ConsistencyViolation(
                    execution_id=execution_id,
                    violation_type="wal_corrupted",
                    description=f"WAL integrity check failed: {e}",
                    details={"error": str(e)},
                )
            )
            return violations

        # Read record
        try:
            record = self.record_store.load(execution_id)
        except FileNotFoundError:
            violations.append(
                ConsistencyViolation(
                    execution_id=execution_id,
                    violation_type="record_missing",
                    description="Record file does not exist",
                    details={},
                )
            )
            return violations
        except Exception as e:
            violations.append(
                ConsistencyViolation(
                    execution_id=execution_id,
                    violation_type="record_corrupted",
                    description=f"Record load failed: {e}",
                    details={"error": str(e)},
                )
            )
            return violations

        # Verify envelope hash consistency
        wal_envelope_hash = None
        for entry in wal_entries:
            if entry.entry_type == WALEntryType.EXECUTION_STARTED:
                wal_envelope_hash = entry.payload.get("envelope_hash")
                break
            elif entry.entry_type == WALEntryType.EXECUTION_CREATED:
                wal_envelope_hash = entry.payload.get("envelope_hash")
                break

        record_envelope_hash = record.header.envelopeHash

        if wal_envelope_hash and record_envelope_hash:
            if wal_envelope_hash != record_envelope_hash:
                violations.append(
                    ConsistencyViolation(
                        execution_id=execution_id,
                        violation_type="envelope_hash_mismatch",
                        description="Envelope hash in WAL does not match record",
                        details={
                            "wal_hash": wal_envelope_hash,
                            "record_hash": record_envelope_hash,
                        },
                    )
                )

        # Verify step completion consistency
        wal_completed_steps = set()
        for entry in wal_entries:
            if entry.entry_type == WALEntryType.STEP_COMPLETED:
                step_id = entry.payload.get("step_id")
                if step_id:
                    wal_completed_steps.add(step_id)

        record_completed_steps = set()
        for event in record.events:
            if event.type == "AGENT_ATTEMPT_END":
                step_id = event.payload.get("step_id")
                if step_id and event.payload.get("status") == "ok":
                    record_completed_steps.add(step_id)

        # Check for missing steps in record
        missing_in_record = wal_completed_steps - record_completed_steps
        if missing_in_record:
            violations.append(
                ConsistencyViolation(
                    execution_id=execution_id,
                    violation_type="steps_missing_in_record",
                    description=f"WAL has completed steps not in record",
                    details={"missing_steps": list(missing_in_record)},
                )
            )

        # Check for extra steps in record
        extra_in_record = record_completed_steps - wal_completed_steps
        if extra_in_record:
            violations.append(
                ConsistencyViolation(
                    execution_id=execution_id,
                    violation_type="extra_steps_in_record",
                    description=f"Record has steps not in WAL",
                    details={"extra_steps": list(extra_in_record)},
                )
            )

        return violations

    def check_all(self) -> dict:
        """
        Check consistency for all executions.

        Returns dict mapping execution_id → violations.
        """
        all_violations = {}

        execution_ids = self.record_store.list_ids()
        for execution_id in execution_ids:
            violations = self.check(execution_id)
            if violations:
                all_violations[execution_id] = violations

        return all_violations
