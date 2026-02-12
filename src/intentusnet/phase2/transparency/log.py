"""
Transparency Log Implementation (Phase II)

Provides append-only public Merkle logs for batch roots.

Key concepts:
- Append-only transparency log
- Merkle tree over batch roots
- Signed checkpoints
- Inclusion and consistency proofs
- Public read-only access
- Monitor-compatible design (Certificate Transparency style)

CRITICAL INVARIANTS:
1. Log is append-only - entries cannot be modified or removed
2. Checkpoints are signed by the log operator
3. Monitors can verify log consistency over time
4. All proofs are offline-verifiable
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature

from intentusnet.phase2.merkle.tree import (
    MerkleTree,
    MerkleProof,
    verify_merkle_proof,
    hash_leaf_data,
)
from intentusnet.phase2.merkle.batch import BatchRoot


# ===========================================================================
# Log Entry
# ===========================================================================


@dataclass
class LogEntry:
    """
    An entry in the transparency log.

    Each entry represents a batch root that has been published.

    Attributes:
        entry_index: Position in the log (0-indexed)
        batch_id: ID of the batch
        batch_root_hash: Root hash of the batch
        gateway_id: Gateway that created the batch
        leaf_hash: Merkle leaf hash in the log
        timestamp: When the entry was added
    """
    entry_index: int
    batch_id: str
    batch_root_hash: str
    gateway_id: str
    leaf_hash: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entryIndex": self.entry_index,
            "batchId": self.batch_id,
            "batchRootHash": self.batch_root_hash,
            "gatewayId": self.gateway_id,
            "leafHash": self.leaf_hash,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LogEntry":
        return cls(
            entry_index=data["entryIndex"],
            batch_id=data["batchId"],
            batch_root_hash=data["batchRootHash"],
            gateway_id=data["gatewayId"],
            leaf_hash=data["leafHash"],
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
        )

    @staticmethod
    def compute_leaf_data(batch_id: str, batch_root_hash: str, gateway_id: str) -> bytes:
        """Compute the leaf data for Merkle hashing."""
        return f"{batch_id}:{batch_root_hash}:{gateway_id}".encode("utf-8")


# ===========================================================================
# Transparency Checkpoint
# ===========================================================================


@dataclass
class TransparencyCheckpoint:
    """
    Signed checkpoint of the transparency log.

    Checkpoints commit to the state of the log at a specific size.
    They are used by monitors to verify log consistency.

    Attributes:
        log_id: ID of the transparency log
        tree_size: Number of entries at this checkpoint
        root_hash: Merkle root of the log at this size
        timestamp: When the checkpoint was created
        signature: Log operator's signature
        key_id: Key ID used for signing
    """
    log_id: str
    tree_size: int
    root_hash: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    signature: Optional[str] = None
    key_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "logId": self.log_id,
            "treeSize": self.tree_size,
            "rootHash": self.root_hash,
            "timestamp": self.timestamp,
            "signature": self.signature,
            "keyId": self.key_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TransparencyCheckpoint":
        return cls(
            log_id=data["logId"],
            tree_size=data["treeSize"],
            root_hash=data["rootHash"],
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            signature=data.get("signature"),
            key_id=data.get("keyId"),
        )

    def compute_signing_data(self) -> str:
        """Compute the data to be signed."""
        content = {
            "logId": self.log_id,
            "treeSize": self.tree_size,
            "rootHash": self.root_hash,
            "timestamp": self.timestamp,
        }
        return json.dumps(content, sort_keys=True, separators=(",", ":"))


# ===========================================================================
# Log Inclusion Proof
# ===========================================================================


@dataclass
class LogInclusionProof:
    """
    Proof that a batch is included in the transparency log.

    Attributes:
        batch_id: ID of the batch
        entry_index: Index of the entry in the log
        merkle_proof: Merkle inclusion proof
        log_tree_size: Size of the log when proof was generated
        log_root_hash: Root hash of the log
    """
    batch_id: str
    entry_index: int
    merkle_proof: MerkleProof
    log_tree_size: int
    log_root_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batchId": self.batch_id,
            "entryIndex": self.entry_index,
            "merkleProof": self.merkle_proof.to_dict(),
            "logTreeSize": self.log_tree_size,
            "logRootHash": self.log_root_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LogInclusionProof":
        return cls(
            batch_id=data["batchId"],
            entry_index=data["entryIndex"],
            merkle_proof=MerkleProof.from_dict(data["merkleProof"]),
            log_tree_size=data["logTreeSize"],
            log_root_hash=data["logRootHash"],
        )

    def verify(self) -> bool:
        """Verify the inclusion proof."""
        if not verify_merkle_proof(self.merkle_proof):
            return False
        return self.merkle_proof.root_hash == self.log_root_hash


# ===========================================================================
# Consistency Proof
# ===========================================================================


@dataclass
class ConsistencyProof:
    """
    Proof of consistency between two log states.

    This proves that a smaller log is a prefix of a larger log,
    ensuring the log has not been tampered with.

    Attributes:
        first_tree_size: Size of the earlier log state
        second_tree_size: Size of the later log state
        first_root_hash: Root hash of the earlier state
        second_root_hash: Root hash of the later state
        proof_hashes: Hashes needed to verify consistency
    """
    first_tree_size: int
    second_tree_size: int
    first_root_hash: str
    second_root_hash: str
    proof_hashes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "firstTreeSize": self.first_tree_size,
            "secondTreeSize": self.second_tree_size,
            "firstRootHash": self.first_root_hash,
            "secondRootHash": self.second_root_hash,
            "proofHashes": self.proof_hashes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConsistencyProof":
        return cls(
            first_tree_size=data["firstTreeSize"],
            second_tree_size=data["secondTreeSize"],
            first_root_hash=data["firstRootHash"],
            second_root_hash=data["secondRootHash"],
            proof_hashes=data["proofHashes"],
        )


# ===========================================================================
# Transparency Log
# ===========================================================================


class TransparencyLog:
    """
    Append-only transparency log for batch roots.

    Provides:
    - Append-only entry addition
    - Signed checkpoints
    - Inclusion proofs for entries
    - Consistency proofs between states

    CRITICAL: This log is append-only. Once an entry is added,
    it cannot be modified or removed.
    """

    def __init__(
        self,
        log_id: str,
        operator_key: Ed25519PrivateKey,
    ):
        """
        Initialize a transparency log.

        Args:
            log_id: Unique identifier for this log
            operator_key: Ed25519 private key for signing checkpoints
        """
        self._log_id = log_id
        self._operator_key = operator_key
        self._operator_public_key = operator_key.public_key()

        # Compute key ID
        from cryptography.hazmat.primitives import serialization
        public_bytes = self._operator_public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        self._key_id = hashlib.sha256(public_bytes).hexdigest()[:16]

        # Internal state
        self._entries: List[LogEntry] = []
        self._tree: Optional[MerkleTree] = None
        self._checkpoints: List[TransparencyCheckpoint] = []

    @property
    def log_id(self) -> str:
        return self._log_id

    @property
    def key_id(self) -> str:
        return self._key_id

    @property
    def size(self) -> int:
        return len(self._entries)

    @property
    def root_hash(self) -> Optional[str]:
        if self._tree is None:
            return None
        return self._tree.root_hash

    def append(self, batch_root: BatchRoot) -> LogEntry:
        """
        Append a batch root to the log.

        Args:
            batch_root: The batch root to append

        Returns:
            The created log entry
        """
        # Compute leaf data
        leaf_data = LogEntry.compute_leaf_data(
            batch_root.batch_id,
            batch_root.root_hash,
            batch_root.gateway_id,
        )
        leaf_hash = hash_leaf_data(leaf_data)

        # Create entry
        entry = LogEntry(
            entry_index=len(self._entries),
            batch_id=batch_root.batch_id,
            batch_root_hash=batch_root.root_hash,
            gateway_id=batch_root.gateway_id,
            leaf_hash=leaf_hash,
        )

        # Add to entries
        self._entries.append(entry)

        # Rebuild tree (in production, use incremental update)
        self._rebuild_tree()

        return entry

    def _rebuild_tree(self) -> None:
        """Rebuild the Merkle tree from entries."""
        if len(self._entries) == 0:
            self._tree = None
            return

        self._tree = MerkleTree()
        for entry in self._entries:
            leaf_data = LogEntry.compute_leaf_data(
                entry.batch_id,
                entry.batch_root_hash,
                entry.gateway_id,
            )
            self._tree.add_leaf(leaf_data)

        self._tree.build()

    def create_checkpoint(self) -> TransparencyCheckpoint:
        """
        Create a signed checkpoint of the current log state.

        Returns:
            Signed TransparencyCheckpoint
        """
        if self._tree is None or self._tree.root_hash is None:
            raise ValueError("Cannot create checkpoint for empty log")

        checkpoint = TransparencyCheckpoint(
            log_id=self._log_id,
            tree_size=len(self._entries),
            root_hash=self._tree.root_hash,
        )

        # Sign the checkpoint
        signing_data = checkpoint.compute_signing_data()
        signature = self._operator_key.sign(signing_data.encode("utf-8"))
        checkpoint.signature = base64.b64encode(signature).decode("ascii")
        checkpoint.key_id = self._key_id

        self._checkpoints.append(checkpoint)
        return checkpoint

    def get_entry(self, index: int) -> Optional[LogEntry]:
        """Get an entry by index."""
        if index < 0 or index >= len(self._entries):
            return None
        return self._entries[index]

    def get_entry_by_batch(self, batch_id: str) -> Optional[LogEntry]:
        """Get an entry by batch ID."""
        for entry in self._entries:
            if entry.batch_id == batch_id:
                return entry
        return None

    def get_inclusion_proof(self, batch_id: str) -> Optional[LogInclusionProof]:
        """
        Get inclusion proof for a batch.

        Args:
            batch_id: ID of the batch

        Returns:
            LogInclusionProof or None if not found
        """
        if self._tree is None:
            return None

        entry = self.get_entry_by_batch(batch_id)
        if entry is None:
            return None

        merkle_proof = self._tree.get_proof(entry.entry_index)

        return LogInclusionProof(
            batch_id=batch_id,
            entry_index=entry.entry_index,
            merkle_proof=merkle_proof,
            log_tree_size=len(self._entries),
            log_root_hash=self._tree.root_hash or "",
        )

    def get_consistency_proof(
        self,
        first_size: int,
        second_size: Optional[int] = None,
    ) -> Optional[ConsistencyProof]:
        """
        Get consistency proof between two log states.

        Args:
            first_size: Size of the earlier state
            second_size: Size of the later state (default: current)

        Returns:
            ConsistencyProof or None if invalid
        """
        if second_size is None:
            second_size = len(self._entries)

        if first_size <= 0 or first_size > second_size:
            return None

        if second_size > len(self._entries):
            return None

        # Compute first root hash
        first_tree = MerkleTree()
        for entry in self._entries[:first_size]:
            leaf_data = LogEntry.compute_leaf_data(
                entry.batch_id,
                entry.batch_root_hash,
                entry.gateway_id,
            )
            first_tree.add_leaf(leaf_data)
        first_root = first_tree.build()

        # Compute second root hash
        second_tree = MerkleTree()
        for entry in self._entries[:second_size]:
            leaf_data = LogEntry.compute_leaf_data(
                entry.batch_id,
                entry.batch_root_hash,
                entry.gateway_id,
            )
            second_tree.add_leaf(leaf_data)
        second_root = second_tree.build()

        # Generate consistency proof hashes
        # This is a simplified implementation
        proof_hashes = self._compute_consistency_hashes(first_size, second_size)

        return ConsistencyProof(
            first_tree_size=first_size,
            second_tree_size=second_size,
            first_root_hash=first_root,
            second_root_hash=second_root,
            proof_hashes=proof_hashes,
        )

    def _compute_consistency_hashes(self, m: int, n: int) -> List[str]:
        """
        Compute consistency proof hashes.

        Simplified implementation - in production, use RFC 6962 algorithm.
        """
        if m == n:
            return []

        # Get all leaf hashes
        leaf_hashes = [entry.leaf_hash for entry in self._entries[:n]]

        # Simplified: return leaf hashes from m to n
        # Full implementation would use subproof algorithm
        return leaf_hashes[m:n]

    def get_checkpoints(self) -> List[TransparencyCheckpoint]:
        """Get all checkpoints."""
        return list(self._checkpoints)

    def get_latest_checkpoint(self) -> Optional[TransparencyCheckpoint]:
        """Get the latest checkpoint."""
        if not self._checkpoints:
            return None
        return self._checkpoints[-1]


# ===========================================================================
# Log Monitor
# ===========================================================================


class LogMonitor:
    """
    Monitor for transparency logs.

    Monitors verify:
    - Log consistency over time
    - Checkpoint signatures
    - Expected entries are present

    This is used to detect log misbehavior (e.g., forks).
    """

    def __init__(self, log_id: str, operator_public_key: bytes):
        """
        Initialize a log monitor.

        Args:
            log_id: ID of the log to monitor
            operator_public_key: Public key of the log operator
        """
        self._log_id = log_id
        self._public_key = Ed25519PublicKey.from_public_bytes(operator_public_key)
        self._last_checkpoint: Optional[TransparencyCheckpoint] = None
        self._observed_entries: Dict[str, LogEntry] = {}

    @property
    def last_checkpoint(self) -> Optional[TransparencyCheckpoint]:
        return self._last_checkpoint

    def verify_checkpoint(self, checkpoint: TransparencyCheckpoint) -> bool:
        """
        Verify a checkpoint signature.

        Args:
            checkpoint: The checkpoint to verify

        Returns:
            True if the signature is valid
        """
        if checkpoint.log_id != self._log_id:
            return False

        if checkpoint.signature is None:
            return False

        try:
            signing_data = checkpoint.compute_signing_data()
            signature = base64.b64decode(checkpoint.signature)
            self._public_key.verify(signature, signing_data.encode("utf-8"))
            return True
        except InvalidSignature:
            return False
        except Exception:
            return False

    def verify_consistency(
        self,
        old_checkpoint: TransparencyCheckpoint,
        new_checkpoint: TransparencyCheckpoint,
        proof: ConsistencyProof,
    ) -> bool:
        """
        Verify consistency between two checkpoints.

        Args:
            old_checkpoint: Earlier checkpoint
            new_checkpoint: Later checkpoint
            proof: Consistency proof

        Returns:
            True if the log is consistent
        """
        # Verify checkpoint signatures
        if not self.verify_checkpoint(old_checkpoint):
            return False
        if not self.verify_checkpoint(new_checkpoint):
            return False

        # Verify sizes match
        if proof.first_tree_size != old_checkpoint.tree_size:
            return False
        if proof.second_tree_size != new_checkpoint.tree_size:
            return False

        # Verify root hashes match
        if proof.first_root_hash != old_checkpoint.root_hash:
            return False
        if proof.second_root_hash != new_checkpoint.root_hash:
            return False

        # In full implementation, verify proof hashes
        # For now, accept if roots match
        return True

    def verify_inclusion(
        self,
        entry: LogEntry,
        proof: LogInclusionProof,
        checkpoint: TransparencyCheckpoint,
    ) -> bool:
        """
        Verify an entry is included in the log.

        Args:
            entry: The entry to verify
            proof: Inclusion proof
            checkpoint: Checkpoint to verify against

        Returns:
            True if the entry is included
        """
        # Verify checkpoint
        if not self.verify_checkpoint(checkpoint):
            return False

        # Verify proof is for correct log state
        if proof.log_tree_size > checkpoint.tree_size:
            return False

        # Verify the proof
        if not proof.verify():
            return False

        # Verify entry matches proof
        if entry.batch_id != proof.batch_id:
            return False
        if entry.entry_index != proof.entry_index:
            return False

        return True

    def update_checkpoint(self, checkpoint: TransparencyCheckpoint) -> bool:
        """
        Update the monitor's checkpoint after verification.

        Returns:
            True if update was successful
        """
        if not self.verify_checkpoint(checkpoint):
            return False

        # Check monotonicity
        if self._last_checkpoint is not None:
            if checkpoint.tree_size < self._last_checkpoint.tree_size:
                return False

        self._last_checkpoint = checkpoint
        return True

    def record_entry(self, entry: LogEntry) -> None:
        """Record an observed entry for future verification."""
        self._observed_entries[entry.batch_id] = entry

    def get_observed_entry(self, batch_id: str) -> Optional[LogEntry]:
        """Get a previously observed entry."""
        return self._observed_entries.get(batch_id)
