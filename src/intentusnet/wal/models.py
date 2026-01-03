"""
WAL data models.

All WAL entries are versioned and include:
- Sequential ordering
- Hash chaining for integrity
- Timestamp (ISO 8601)
- Type classification
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Literal
from enum import Enum
import hashlib
import json


class WALEntryType(str, Enum):
    """
    WAL entry types (stable schema versioning).
    """

    # Execution lifecycle (production state machine)
    EXECUTION_CREATED = "execution.created"
    EXECUTION_STARTED = "execution.started"
    EXECUTION_IN_PROGRESS = "execution.in_progress"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"
    EXECUTION_ABORTED = "execution.aborted"
    EXECUTION_STATE_TRANSITION = "execution.state_transition"

    # Step lifecycle
    STEP_STARTED = "step.started"
    STEP_COMPLETED = "step.completed"
    STEP_FAILED = "step.failed"
    STEP_SKIPPED = "step.skipped"

    # Fallback decisions
    FALLBACK_TRIGGERED = "fallback.triggered"
    FALLBACK_EXHAUSTED = "fallback.exhausted"

    # Contract enforcement
    CONTRACT_VALIDATED = "contract.validated"
    CONTRACT_VIOLATED = "contract.violated"

    # Recovery
    RECOVERY_STARTED = "recovery.started"
    RECOVERY_COMPLETED = "recovery.completed"

    # Checkpoint
    CHECKPOINT = "checkpoint"

    # Idempotency
    IDEMPOTENCY_CHECK = "idempotency.check"
    IDEMPOTENCY_DUPLICATE = "idempotency.duplicate"

    # Locking
    LOCK_ACQUIRED = "lock.acquired"
    LOCK_RELEASED = "lock.released"
    LOCK_STALE_DETECTED = "lock.stale_detected"

    # Agent invocation
    AGENT_INVOCATION_START = "agent.invocation_start"
    AGENT_INVOCATION_END = "agent.invocation_end"


class ExecutionState(str, Enum):
    """
    Execution lifecycle states (production state machine).

    Legal transitions:
    - CREATED → STARTED
    - STARTED → IN_PROGRESS
    - IN_PROGRESS → COMPLETED | FAILED | ABORTED
    - FAILED → RECOVERING
    - RECOVERING → IN_PROGRESS | ABORTED

    Terminal states: COMPLETED, ABORTED
    """

    CREATED = "created"
    STARTED = "started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"
    RECOVERING = "recovering"

    @classmethod
    def is_terminal(cls, state: "ExecutionState") -> bool:
        """Check if state is terminal (no further transitions)."""
        return state in {cls.COMPLETED, cls.ABORTED}

    @classmethod
    def validate_transition(cls, from_state: "ExecutionState", to_state: "ExecutionState") -> bool:
        """
        Validate state transition.

        Returns True if transition is legal, False otherwise.
        """
        legal_transitions = {
            cls.CREATED: {cls.STARTED},
            cls.STARTED: {cls.IN_PROGRESS},
            cls.IN_PROGRESS: {cls.COMPLETED, cls.FAILED, cls.ABORTED},
            cls.FAILED: {cls.RECOVERING, cls.ABORTED},
            cls.RECOVERING: {cls.IN_PROGRESS, cls.ABORTED},
            cls.COMPLETED: set(),  # Terminal
            cls.ABORTED: set(),    # Terminal
        }

        return to_state in legal_transitions.get(from_state, set())


@dataclass
class WALEntry:
    """
    Single WAL entry (append-only record).

    All WAL entries are immutable once written.
    Hash chaining ensures integrity.
    """

    # Core fields
    seq: int  # Monotonic sequence number (deterministic ordering)
    execution_id: str  # Execution identifier
    timestamp_iso: str  # ISO 8601 timestamp
    entry_type: WALEntryType  # Entry classification

    # Payload
    payload: Dict[str, Any]  # Entry-specific data

    # Integrity
    prev_hash: Optional[str] = None  # Hash of previous entry (chain)
    entry_hash: Optional[str] = None  # Hash of this entry

    # Metadata
    version: str = "1.0"  # WAL schema version

    def compute_hash(self) -> str:
        """
        Compute deterministic hash for this entry.
        Hash includes: seq, execution_id, entry_type, payload, prev_hash.
        """
        data = {
            "seq": self.seq,
            "execution_id": self.execution_id,
            "timestamp_iso": self.timestamp_iso,
            "entry_type": self.entry_type.value,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "version": self.version,
        }
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize to JSON-compatible dict.
        """
        return {
            "seq": self.seq,
            "execution_id": self.execution_id,
            "timestamp_iso": self.timestamp_iso,
            "entry_type": self.entry_type.value,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WALEntry:
        """
        Deserialize from JSON.
        """
        return cls(
            seq=data["seq"],
            execution_id=data["execution_id"],
            timestamp_iso=data["timestamp_iso"],
            entry_type=WALEntryType(data["entry_type"]),
            payload=data["payload"],
            prev_hash=data.get("prev_hash"),
            entry_hash=data.get("entry_hash"),
            version=data.get("version", "1.0"),
        )


@dataclass
class ExecutionCheckpoint:
    """
    Execution state checkpoint (for recovery).
    """

    execution_id: str
    state: ExecutionState
    last_wal_seq: int
    last_wal_hash: str
    completed_steps: list[str] = field(default_factory=list)
    pending_steps: list[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
