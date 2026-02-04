"""
Merkle-Rooted Execution Batches Module (Phase II)

Provides cryptographic batching of executions with Merkle proofs.

Key concepts:
- Deterministic leaf definition
- Stable ordering rules
- Batch root signing
- Batch witness attestations
- Execution inclusion proofs
- Batch immutability guarantees
"""

from intentusnet.phase2.merkle.batch import (
    ExecutionBatch,
    BatchLeaf,
    BatchRoot,
    BatchInclusionProof,
    BatchWitnessAttestation,
    BatchBuilder,
    BatchVerifier,
)

from intentusnet.phase2.merkle.tree import (
    MerkleTree,
    MerkleNode,
    MerkleProof,
    compute_merkle_root,
    verify_merkle_proof,
)

__all__ = [
    # Batch types
    "ExecutionBatch",
    "BatchLeaf",
    "BatchRoot",
    "BatchInclusionProof",
    "BatchWitnessAttestation",
    "BatchBuilder",
    "BatchVerifier",
    # Merkle primitives
    "MerkleTree",
    "MerkleNode",
    "MerkleProof",
    "compute_merkle_root",
    "verify_merkle_proof",
]
