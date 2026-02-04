"""
WAL data models.

All WAL entries are versioned and include:
- Sequential ordering
- Hash chaining for integrity
- Timestamp (ISO 8601)
- Type classification

Phase I REGULATED mode additions:
- Ed25519 signature over entry_hash
- Key ID for signature verification
- Signature verification MUST pass in REGULATED mode
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Literal, Protocol
from enum import Enum
import hashlib
import json


# ===========================================================================
# Signing Protocol (Phase I REGULATED)
# ===========================================================================

class WALSigner(Protocol):
    """
    Protocol for WAL entry signing.

    Implementations MUST:
    - Use Ed25519 or equivalent (256-bit security)
    - Return deterministic signatures for same input
    - Provide key_id for verification lookup
    """

    @property
    def key_id(self) -> str:
        """Unique identifier for the signing key."""
        ...

    def sign(self, data: bytes) -> bytes:
        """Sign data, return raw signature bytes."""
        ...


class WALVerifier(Protocol):
    """
    Protocol for WAL signature verification.

    Implementations MUST:
    - Support offline verification (no network required)
    - Fail explicitly on invalid signatures
    """

    def verify(self, data: bytes, signature: bytes, key_id: str) -> bool:
        """Verify signature. Returns True if valid, False if invalid."""
        ...

    def get_public_key(self, key_id: str) -> Optional[bytes]:
        """Get public key for key_id. Returns None if not found."""
        ...


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


class WALSignatureError(RuntimeError):
    """Raised when WAL signature is invalid or missing in REGULATED mode."""
    pass


@dataclass
class WALEntry:
    """
    Single WAL entry (append-only record).

    All WAL entries are immutable once written.
    Hash chaining ensures integrity.

    Phase I REGULATED mode:
    - signature: Ed25519 signature over entry_hash (base64)
    - signer_key_id: Key identifier for verification
    Both MUST be present and valid in REGULATED mode.
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

    # Signature (Phase I REGULATED)
    signature: Optional[str] = None  # Base64-encoded Ed25519 signature
    signer_key_id: Optional[str] = None  # Key identifier for verification

    # Metadata
    version: str = "1.0"  # WAL schema version

    @property
    def is_signed(self) -> bool:
        """Check if entry has signature fields populated."""
        return self.signature is not None and self.signer_key_id is not None

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
        Includes signature fields if present (Phase I REGULATED).
        """
        result = {
            "seq": self.seq,
            "execution_id": self.execution_id,
            "timestamp_iso": self.timestamp_iso,
            "entry_type": self.entry_type.value,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
            "version": self.version,
        }

        # Include signature fields only if present (Phase I REGULATED)
        if self.signature is not None:
            result["signature"] = self.signature
        if self.signer_key_id is not None:
            result["signer_key_id"] = self.signer_key_id

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WALEntry:
        """
        Deserialize from JSON.
        Handles both signed and unsigned entries.
        """
        return cls(
            seq=data["seq"],
            execution_id=data["execution_id"],
            timestamp_iso=data["timestamp_iso"],
            entry_type=WALEntryType(data["entry_type"]),
            payload=data["payload"],
            prev_hash=data.get("prev_hash"),
            entry_hash=data.get("entry_hash"),
            signature=data.get("signature"),  # Phase I REGULATED
            signer_key_id=data.get("signer_key_id"),  # Phase I REGULATED
            version=data.get("version", "1.0"),
        )

    def sign(self, signer: "WALSigner") -> None:
        """
        Sign this entry using the provided signer.

        MUST be called after compute_hash().
        Sets signature and signer_key_id fields.

        Args:
            signer: WALSigner implementation (Ed25519)

        Raises:
            ValueError: If entry_hash is not set
        """
        if not self.entry_hash:
            raise ValueError("Cannot sign entry without entry_hash. Call compute_hash() first.")

        signature_bytes = signer.sign(self.entry_hash.encode("utf-8"))
        import base64
        self.signature = base64.b64encode(signature_bytes).decode("ascii")
        self.signer_key_id = signer.key_id

    def verify_signature(self, verifier: "WALVerifier") -> bool:
        """
        Verify this entry's signature.

        Args:
            verifier: WALVerifier implementation

        Returns:
            True if signature is valid, False otherwise

        Raises:
            WALSignatureError: If signature fields are missing
        """
        if not self.is_signed:
            raise WALSignatureError(
                f"Entry seq={self.seq} is not signed. "
                "Signature verification requires signature and signer_key_id."
            )

        if not self.entry_hash:
            raise WALSignatureError(
                f"Entry seq={self.seq} has no entry_hash. Cannot verify signature."
            )

        import base64
        try:
            signature_bytes = base64.b64decode(self.signature)
        except Exception as e:
            raise WALSignatureError(f"Invalid signature encoding: {e}")

        return verifier.verify(
            self.entry_hash.encode("utf-8"),
            signature_bytes,
            self.signer_key_id
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
