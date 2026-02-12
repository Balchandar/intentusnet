"""
Merkle-Rooted Execution Batches (Phase II)

Provides cryptographic batching of executions with Merkle proofs.

Key concepts:
- Deterministic leaf definition (canonical hash of execution)
- Stable ordering rules (lexicographic by execution ID)
- Batch root signing by gateway
- Batch witness attestations
- Execution inclusion proofs
- Batch immutability guarantees

CRITICAL INVARIANTS:
1. Batch contents are immutable after signing
2. Leaf ordering is deterministic and verifiable
3. Inclusion proofs are offline-verifiable
4. Batches can only be created by gateways
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from intentusnet.phase2.gateway.enforcement import (
    CanonicalExecutionEnvelope,
    GatewaySigner,
    GatewaySignature,
)
from intentusnet.phase2.merkle.tree import (
    MerkleTree,
    MerkleProof,
    verify_merkle_proof,
    hash_leaf_data,
)
from intentusnet.phase2.witness.attestation import (
    WitnessAttestation,
)


# ===========================================================================
# Batch Leaf
# ===========================================================================


@dataclass(frozen=True)
class BatchLeaf:
    """
    A leaf in an execution batch Merkle tree.

    The leaf represents a single execution's commitment in the batch.

    Attributes:
        execution_id: ID of the execution
        canonical_hash: Canonical hash of the execution
        leaf_hash: Merkle leaf hash (SHA-256 of leaf data)
        leaf_index: Position in the batch
    """
    execution_id: str
    canonical_hash: str
    leaf_hash: str
    leaf_index: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "executionId": self.execution_id,
            "canonicalHash": self.canonical_hash,
            "leafHash": self.leaf_hash,
            "leafIndex": self.leaf_index,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BatchLeaf":
        return cls(
            execution_id=data["executionId"],
            canonical_hash=data["canonicalHash"],
            leaf_hash=data["leafHash"],
            leaf_index=data["leafIndex"],
        )

    @staticmethod
    def compute_leaf_data(execution_id: str, canonical_hash: str) -> bytes:
        """
        Compute the leaf data for Merkle hashing.

        Leaf data is: execution_id || ":" || canonical_hash
        """
        return f"{execution_id}:{canonical_hash}".encode("utf-8")


# ===========================================================================
# Batch Root
# ===========================================================================


@dataclass
class BatchRoot:
    """
    Signed root of an execution batch.

    Attributes:
        batch_id: Unique identifier for the batch
        root_hash: Merkle root hash
        leaf_count: Number of executions in the batch
        gateway_id: ID of the gateway that created the batch
        signature: Gateway signature over the batch root
        created_at: When the batch was created
        sealed_at: When the batch was sealed (signed)
    """
    batch_id: str
    root_hash: str
    leaf_count: int
    gateway_id: str
    signature: Optional[GatewaySignature] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sealed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batchId": self.batch_id,
            "rootHash": self.root_hash,
            "leafCount": self.leaf_count,
            "gatewayId": self.gateway_id,
            "signature": self.signature.to_dict() if self.signature else None,
            "createdAt": self.created_at,
            "sealedAt": self.sealed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BatchRoot":
        sig_data = data.get("signature")
        return cls(
            batch_id=data["batchId"],
            root_hash=data["rootHash"],
            leaf_count=data["leafCount"],
            gateway_id=data["gatewayId"],
            signature=GatewaySignature.from_dict(sig_data) if sig_data else None,
            created_at=data.get("createdAt", datetime.now(timezone.utc).isoformat()),
            sealed_at=data.get("sealedAt"),
        )

    def compute_signing_data(self) -> str:
        """Compute the data to be signed for the batch root."""
        content = {
            "batchId": self.batch_id,
            "rootHash": self.root_hash,
            "leafCount": self.leaf_count,
            "gatewayId": self.gateway_id,
            "createdAt": self.created_at,
        }
        return json.dumps(content, sort_keys=True, separators=(",", ":"))

    def is_sealed(self) -> bool:
        """Check if the batch has been sealed (signed)."""
        return self.signature is not None and self.sealed_at is not None


# ===========================================================================
# Batch Inclusion Proof
# ===========================================================================


@dataclass
class BatchInclusionProof:
    """
    Proof that an execution is included in a batch.

    This proof can be verified offline using only the batch root.

    Attributes:
        execution_id: ID of the execution
        canonical_hash: Canonical hash of the execution
        batch_id: ID of the batch
        batch_root_hash: Root hash of the batch
        merkle_proof: Merkle inclusion proof
        leaf: The batch leaf for this execution
    """
    execution_id: str
    canonical_hash: str
    batch_id: str
    batch_root_hash: str
    merkle_proof: MerkleProof
    leaf: BatchLeaf

    def to_dict(self) -> Dict[str, Any]:
        return {
            "executionId": self.execution_id,
            "canonicalHash": self.canonical_hash,
            "batchId": self.batch_id,
            "batchRootHash": self.batch_root_hash,
            "merkleProof": self.merkle_proof.to_dict(),
            "leaf": self.leaf.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BatchInclusionProof":
        return cls(
            execution_id=data["executionId"],
            canonical_hash=data["canonicalHash"],
            batch_id=data["batchId"],
            batch_root_hash=data["batchRootHash"],
            merkle_proof=MerkleProof.from_dict(data["merkleProof"]),
            leaf=BatchLeaf.from_dict(data["leaf"]),
        )

    def verify(self) -> bool:
        """
        Verify the inclusion proof.

        Returns:
            True if the proof is valid
        """
        # Verify the Merkle proof
        if not verify_merkle_proof(self.merkle_proof):
            return False

        # Verify the leaf hash matches the execution
        expected_leaf_data = BatchLeaf.compute_leaf_data(
            self.execution_id,
            self.canonical_hash,
        )
        expected_leaf_hash = hash_leaf_data(expected_leaf_data)

        if expected_leaf_hash != self.leaf.leaf_hash:
            return False

        # Verify root hash matches
        if self.merkle_proof.root_hash != self.batch_root_hash:
            return False

        return True


# ===========================================================================
# Batch Witness Attestation
# ===========================================================================


@dataclass
class BatchWitnessAttestation:
    """
    Witness attestation for a batch.

    Witnesses can attest to the validity of entire batches,
    not just individual executions.

    Attributes:
        attestation_id: Unique identifier
        batch_id: ID of the attested batch
        batch_root_hash: Root hash that was verified
        witness_attestations: Individual witness attestations
        created_at: When this batch attestation was created
    """
    attestation_id: str
    batch_id: str
    batch_root_hash: str
    witness_attestations: List[WitnessAttestation] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attestationId": self.attestation_id,
            "batchId": self.batch_id,
            "batchRootHash": self.batch_root_hash,
            "witnessAttestations": [a.to_dict() for a in self.witness_attestations],
            "createdAt": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BatchWitnessAttestation":
        return cls(
            attestation_id=data["attestationId"],
            batch_id=data["batchId"],
            batch_root_hash=data["batchRootHash"],
            witness_attestations=[
                WitnessAttestation.from_dict(a)
                for a in data.get("witnessAttestations", [])
            ],
            created_at=data.get("createdAt", datetime.now(timezone.utc).isoformat()),
        )

    def add_attestation(self, attestation: WitnessAttestation) -> None:
        """Add a witness attestation."""
        for existing in self.witness_attestations:
            if existing.witness_id == attestation.witness_id:
                raise ValueError(
                    f"Witness {attestation.witness_id} has already attested"
                )
        self.witness_attestations.append(attestation)


# ===========================================================================
# Execution Batch
# ===========================================================================


@dataclass
class ExecutionBatch:
    """
    A batch of executions with Merkle root.

    Batches are immutable after sealing.

    Attributes:
        batch_id: Unique identifier
        gateway_id: Gateway that created this batch
        leaves: Ordered list of batch leaves
        root: Signed batch root (after sealing)
        merkle_tree: The Merkle tree (internal)
        witness_attestation: Optional batch-level witness attestation
        created_at: When the batch was created
        sealed: Whether the batch is sealed
    """
    batch_id: str
    gateway_id: str
    leaves: List[BatchLeaf] = field(default_factory=list)
    root: Optional[BatchRoot] = None
    witness_attestation: Optional[BatchWitnessAttestation] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sealed: bool = False

    # Internal state (not serialized)
    _merkle_tree: Optional[MerkleTree] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batchId": self.batch_id,
            "gatewayId": self.gateway_id,
            "leaves": [l.to_dict() for l in self.leaves],
            "root": self.root.to_dict() if self.root else None,
            "witnessAttestation": (
                self.witness_attestation.to_dict()
                if self.witness_attestation else None
            ),
            "createdAt": self.created_at,
            "sealed": self.sealed,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionBatch":
        root_data = data.get("root")
        wa_data = data.get("witnessAttestation")

        return cls(
            batch_id=data["batchId"],
            gateway_id=data["gatewayId"],
            leaves=[BatchLeaf.from_dict(l) for l in data.get("leaves", [])],
            root=BatchRoot.from_dict(root_data) if root_data else None,
            witness_attestation=(
                BatchWitnessAttestation.from_dict(wa_data)
                if wa_data else None
            ),
            created_at=data.get("createdAt", datetime.now(timezone.utc).isoformat()),
            sealed=data.get("sealed", False),
        )

    def get_inclusion_proof(self, execution_id: str) -> Optional[BatchInclusionProof]:
        """
        Get inclusion proof for an execution.

        Args:
            execution_id: ID of the execution

        Returns:
            BatchInclusionProof or None if not found
        """
        if not self.sealed or self._merkle_tree is None or self.root is None:
            return None

        # Find the leaf
        leaf = None
        for l in self.leaves:
            if l.execution_id == execution_id:
                leaf = l
                break

        if leaf is None:
            return None

        # Get Merkle proof
        merkle_proof = self._merkle_tree.get_proof(leaf.leaf_index)

        return BatchInclusionProof(
            execution_id=execution_id,
            canonical_hash=leaf.canonical_hash,
            batch_id=self.batch_id,
            batch_root_hash=self.root.root_hash,
            merkle_proof=merkle_proof,
            leaf=leaf,
        )

    def contains_execution(self, execution_id: str) -> bool:
        """Check if the batch contains an execution."""
        return any(l.execution_id == execution_id for l in self.leaves)


# ===========================================================================
# Batch Builder
# ===========================================================================


class BatchBuilder:
    """
    Builder for creating execution batches.

    Batches are built by:
    1. Adding executions
    2. Building the Merkle tree
    3. Signing the batch root

    Once sealed, the batch is immutable.
    """

    def __init__(self, gateway_id: str, batch_id: Optional[str] = None):
        self._gateway_id = gateway_id
        self._batch_id = batch_id or str(uuid.uuid4())
        self._executions: List[Tuple[str, str]] = []  # (execution_id, canonical_hash)
        self._sealed = False
        self._batch: Optional[ExecutionBatch] = None

    @property
    def batch_id(self) -> str:
        return self._batch_id

    @property
    def execution_count(self) -> int:
        return len(self._executions)

    def add_execution(self, envelope: CanonicalExecutionEnvelope) -> int:
        """
        Add an execution to the batch.

        Returns the index of the execution in the batch.

        Raises:
            RuntimeError: If batch is already sealed
        """
        if self._sealed:
            raise RuntimeError("Cannot add executions to sealed batch")

        # Check for duplicates
        for exec_id, _ in self._executions:
            if exec_id == envelope.execution_id:
                raise ValueError(
                    f"Execution {envelope.execution_id} already in batch"
                )

        self._executions.append((envelope.execution_id, envelope.canonical_hash))
        return len(self._executions) - 1

    def add_execution_by_hash(self, execution_id: str, canonical_hash: str) -> int:
        """
        Add an execution to the batch by ID and hash.

        This is useful when you don't have the full envelope.
        """
        if self._sealed:
            raise RuntimeError("Cannot add executions to sealed batch")

        for exec_id, _ in self._executions:
            if exec_id == execution_id:
                raise ValueError(f"Execution {execution_id} already in batch")

        self._executions.append((execution_id, canonical_hash))
        return len(self._executions) - 1

    def build_and_seal(self, signer: GatewaySigner) -> ExecutionBatch:
        """
        Build the Merkle tree and seal the batch.

        Args:
            signer: Gateway signer for signing the batch root

        Returns:
            The sealed ExecutionBatch

        Raises:
            ValueError: If batch has no executions
            RuntimeError: If batch is already sealed
        """
        if self._sealed:
            raise RuntimeError("Batch is already sealed")

        if len(self._executions) == 0:
            raise ValueError("Cannot seal empty batch")

        # Sort executions by ID for deterministic ordering
        sorted_executions = sorted(self._executions, key=lambda x: x[0])

        # Build Merkle tree
        tree = MerkleTree()
        leaves: List[BatchLeaf] = []

        for i, (exec_id, canonical_hash) in enumerate(sorted_executions):
            leaf_data = BatchLeaf.compute_leaf_data(exec_id, canonical_hash)
            leaf_index = tree.add_leaf(leaf_data)
            leaf_hash = hash_leaf_data(leaf_data)

            leaves.append(BatchLeaf(
                execution_id=exec_id,
                canonical_hash=canonical_hash,
                leaf_hash=leaf_hash,
                leaf_index=leaf_index,
            ))

        root_hash = tree.build()

        # Create batch root
        batch_root = BatchRoot(
            batch_id=self._batch_id,
            root_hash=root_hash,
            leaf_count=len(leaves),
            gateway_id=self._gateway_id,
        )

        # Sign the batch root
        signing_data = batch_root.compute_signing_data()
        signature_bytes = signer.sign(signing_data.encode("utf-8"))

        batch_root.signature = GatewaySignature(
            key_id=signer.key_id,
            signature=base64.b64encode(signature_bytes).decode("ascii"),
            canonical_hash=hashlib.sha256(signing_data.encode("utf-8")).hexdigest(),
        )
        batch_root.sealed_at = datetime.now(timezone.utc).isoformat()

        # Create batch
        self._batch = ExecutionBatch(
            batch_id=self._batch_id,
            gateway_id=self._gateway_id,
            leaves=leaves,
            root=batch_root,
            sealed=True,
        )
        self._batch._merkle_tree = tree

        self._sealed = True
        return self._batch


# ===========================================================================
# Batch Verifier
# ===========================================================================


class BatchVerifier:
    """
    Verifier for execution batches.

    Provides verification of:
    - Batch root signatures
    - Inclusion proofs
    - Batch consistency
    """

    def __init__(self, gateway_public_keys: Dict[str, bytes]):
        """
        Initialize the verifier.

        Args:
            gateway_public_keys: Map of key_id to public key bytes
        """
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        self._public_keys: Dict[str, Ed25519PublicKey] = {}
        for key_id, key_bytes in gateway_public_keys.items():
            self._public_keys[key_id] = Ed25519PublicKey.from_public_bytes(key_bytes)

    def add_gateway_key(self, key_id: str, public_key_bytes: bytes) -> None:
        """Add a gateway public key."""
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        self._public_keys[key_id] = Ed25519PublicKey.from_public_bytes(public_key_bytes)

    def verify_batch_signature(self, batch: ExecutionBatch) -> bool:
        """
        Verify the batch root signature.

        Returns:
            True if the signature is valid
        """
        if batch.root is None or batch.root.signature is None:
            return False

        key_id = batch.root.signature.key_id
        if key_id not in self._public_keys:
            return False

        try:
            from cryptography.exceptions import InvalidSignature

            signing_data = batch.root.compute_signing_data()
            signature = base64.b64decode(batch.root.signature.signature)
            self._public_keys[key_id].verify(signature, signing_data.encode("utf-8"))
            return True
        except InvalidSignature:
            return False
        except Exception:
            return False

    def verify_inclusion_proof(self, proof: BatchInclusionProof) -> bool:
        """
        Verify an inclusion proof.

        Returns:
            True if the proof is valid
        """
        return proof.verify()

    def verify_batch_consistency(self, batch: ExecutionBatch) -> bool:
        """
        Verify batch internal consistency.

        Checks:
        - All leaves are present
        - Leaf ordering is correct
        - Root hash matches computed root

        Returns:
            True if the batch is consistent
        """
        if batch.root is None:
            return False

        if len(batch.leaves) != batch.root.leaf_count:
            return False

        # Verify leaf ordering (should be sorted by execution ID)
        sorted_ids = sorted(l.execution_id for l in batch.leaves)
        actual_ids = [l.execution_id for l in batch.leaves]
        if sorted_ids != actual_ids:
            return False

        # Recompute root hash
        tree = MerkleTree()
        for leaf in batch.leaves:
            leaf_data = BatchLeaf.compute_leaf_data(
                leaf.execution_id,
                leaf.canonical_hash,
            )
            tree.add_leaf(leaf_data)

        computed_root = tree.build()
        return computed_root == batch.root.root_hash
