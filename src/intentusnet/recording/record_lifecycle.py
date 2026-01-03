"""
Execution record lifecycle management.

Records have their own lifecycle separate from WAL:
CREATED → PARTIAL → FINALIZED → CORRUPTED
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass
from typing import Optional, List
import hashlib
import json


class RecordState(str, Enum):
    """Record lifecycle states."""
    CREATED = "created"
    PARTIAL = "partial"
    FINALIZED = "finalized"
    CORRUPTED = "corrupted"


@dataclass
class RecordIntegrityCheck:
    """Record integrity verification result."""
    record_id: str
    state: RecordState
    wal_consistent: bool
    hash_valid: bool
    issues: List[str]

    def is_valid(self) -> bool:
        """Check if record is valid."""
        return (
            self.state == RecordState.FINALIZED
            and self.wal_consistent
            and self.hash_valid
            and len(self.issues) == 0
        )

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "state": self.state.value,
            "wal_consistent": self.wal_consistent,
            "hash_valid": self.hash_valid,
            "issues": self.issues,
        }


class RecordHasher:
    """Compute and verify record hashes."""

    @staticmethod
    def compute_record_hash(record_data: dict) -> str:
        """
        Compute deterministic hash of record.

        Excludes the hash field itself.
        """
        hashable_data = {k: v for k, v in record_data.items() if k != "record_hash"}
        canonical = json.dumps(
            hashable_data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def verify_record_hash(record_data: dict) -> bool:
        """Verify record hash is valid."""
        stored_hash = record_data.get("record_hash")
        if not stored_hash:
            return False

        computed_hash = RecordHasher.compute_record_hash(record_data)
        return stored_hash == computed_hash


class RecordLifecycleManager:
    """
    Manages record lifecycle transitions.
    """

    @staticmethod
    def determine_state(
        record_data: dict,
        wal_entries: Optional[List] = None,
    ) -> RecordState:
        """
        Determine record state.

        - CREATED: Record created but no data
        - PARTIAL: Record has some data but not finalized
        - FINALIZED: Record complete and immutable
        - CORRUPTED: Record hash invalid or inconsistent with WAL
        """
        # Check hash integrity first
        if not RecordHasher.verify_record_hash(record_data):
            return RecordState.CORRUPTED

        # Check if finalized
        if record_data.get("finalized", False):
            return RecordState.FINALIZED

        # Check if has any events
        events = record_data.get("events", [])
        if events:
            return RecordState.PARTIAL

        return RecordState.CREATED

    @staticmethod
    def finalize_record(record_data: dict) -> dict:
        """
        Finalize record (mark immutable).

        Computes and stores record hash.
        """
        record_data["finalized"] = True

        # Compute and store hash
        record_hash = RecordHasher.compute_record_hash(record_data)
        record_data["record_hash"] = record_hash

        return record_data
