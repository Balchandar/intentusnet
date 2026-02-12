"""
Merkle Tree Implementation (Phase II)

Provides cryptographic Merkle tree primitives for execution batching.

Key features:
- SHA-256 based Merkle tree
- Deterministic leaf ordering
- Efficient inclusion proofs
- Verification of proofs
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# ===========================================================================
# Merkle Node
# ===========================================================================


@dataclass
class MerkleNode:
    """
    A node in a Merkle tree.

    Attributes:
        hash: SHA-256 hash of this node
        left: Left child (None for leaves)
        right: Right child (None for leaves)
        data: Original data (only for leaves)
        index: Leaf index (only for leaves)
    """
    hash: str
    left: Optional["MerkleNode"] = None
    right: Optional["MerkleNode"] = None
    data: Optional[bytes] = None
    index: Optional[int] = None

    def is_leaf(self) -> bool:
        """Check if this is a leaf node."""
        return self.left is None and self.right is None


# ===========================================================================
# Merkle Proof
# ===========================================================================


@dataclass
class MerkleProof:
    """
    Inclusion proof for a leaf in a Merkle tree.

    The proof consists of sibling hashes along the path from leaf to root.

    Attributes:
        leaf_hash: Hash of the leaf being proved
        leaf_index: Index of the leaf
        proof_hashes: List of sibling hashes (from leaf to root)
        directions: List of directions (True = left sibling, False = right sibling)
        root_hash: Expected root hash
    """
    leaf_hash: str
    leaf_index: int
    proof_hashes: List[str]
    directions: List[bool]  # True = sibling is on left, False = sibling is on right
    root_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "leafHash": self.leaf_hash,
            "leafIndex": self.leaf_index,
            "proofHashes": self.proof_hashes,
            "directions": self.directions,
            "rootHash": self.root_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MerkleProof":
        return cls(
            leaf_hash=data["leafHash"],
            leaf_index=data["leafIndex"],
            proof_hashes=data["proofHashes"],
            directions=data["directions"],
            root_hash=data["rootHash"],
        )


# ===========================================================================
# Hash Functions
# ===========================================================================


def _hash_leaf(data: bytes) -> str:
    """
    Hash a leaf node.

    Leaf nodes are prefixed with 0x00 to prevent second-preimage attacks.
    """
    hasher = hashlib.sha256()
    hasher.update(b"\x00")  # Leaf prefix
    hasher.update(data)
    return hasher.hexdigest()


def _hash_internal(left: str, right: str) -> str:
    """
    Hash an internal node.

    Internal nodes are prefixed with 0x01 to prevent second-preimage attacks.
    """
    hasher = hashlib.sha256()
    hasher.update(b"\x01")  # Internal prefix
    hasher.update(bytes.fromhex(left))
    hasher.update(bytes.fromhex(right))
    return hasher.hexdigest()


# ===========================================================================
# Merkle Tree
# ===========================================================================


class MerkleTree:
    """
    Merkle tree implementation for execution batching.

    Features:
    - SHA-256 based hashing
    - Domain separation for leaves vs internal nodes
    - Efficient inclusion proofs
    - Deterministic construction
    """

    def __init__(self):
        self._leaves: List[MerkleNode] = []
        self._root: Optional[MerkleNode] = None
        self._built = False

    @property
    def root(self) -> Optional[MerkleNode]:
        return self._root

    @property
    def root_hash(self) -> Optional[str]:
        return self._root.hash if self._root else None

    @property
    def leaf_count(self) -> int:
        return len(self._leaves)

    def add_leaf(self, data: bytes) -> int:
        """
        Add a leaf to the tree.

        Returns the index of the added leaf.
        """
        if self._built:
            raise RuntimeError("Cannot add leaves after tree is built")

        leaf_hash = _hash_leaf(data)
        index = len(self._leaves)
        leaf = MerkleNode(
            hash=leaf_hash,
            data=data,
            index=index,
        )
        self._leaves.append(leaf)
        return index

    def build(self) -> str:
        """
        Build the Merkle tree and return the root hash.

        Raises:
            ValueError: If tree has no leaves
        """
        if len(self._leaves) == 0:
            raise ValueError("Cannot build tree with no leaves")

        if self._built:
            return self._root.hash if self._root else ""

        # Handle single leaf case
        if len(self._leaves) == 1:
            self._root = self._leaves[0]
            self._built = True
            return self._root.hash

        # Build tree bottom-up
        current_level = list(self._leaves)

        while len(current_level) > 1:
            next_level: List[MerkleNode] = []

            # Process pairs
            for i in range(0, len(current_level), 2):
                left = current_level[i]

                # If odd number of nodes, duplicate the last one
                if i + 1 >= len(current_level):
                    right = left
                else:
                    right = current_level[i + 1]

                parent_hash = _hash_internal(left.hash, right.hash)
                parent = MerkleNode(
                    hash=parent_hash,
                    left=left,
                    right=right,
                )
                next_level.append(parent)

            current_level = next_level

        self._root = current_level[0]
        self._built = True
        return self._root.hash

    def get_proof(self, index: int) -> MerkleProof:
        """
        Get inclusion proof for a leaf.

        Args:
            index: Index of the leaf

        Returns:
            MerkleProof for the leaf

        Raises:
            ValueError: If tree not built or index invalid
        """
        if not self._built:
            raise ValueError("Tree must be built before generating proofs")

        if index < 0 or index >= len(self._leaves):
            raise ValueError(f"Invalid leaf index: {index}")

        leaf = self._leaves[index]
        proof_hashes: List[str] = []
        directions: List[bool] = []

        # Build proof by finding path from leaf to root
        current_level = list(self._leaves)
        current_index = index

        while len(current_level) > 1:
            # Find sibling
            if current_index % 2 == 0:
                # Current is left child, sibling is right
                sibling_index = current_index + 1
                if sibling_index >= len(current_level):
                    sibling_index = current_index  # Duplicate
                directions.append(False)  # Sibling is on right
            else:
                # Current is right child, sibling is left
                sibling_index = current_index - 1
                directions.append(True)  # Sibling is on left

            proof_hashes.append(current_level[sibling_index].hash)

            # Move to parent level
            next_level: List[MerkleNode] = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                if i + 1 >= len(current_level):
                    right = left
                else:
                    right = current_level[i + 1]

                parent_hash = _hash_internal(left.hash, right.hash)
                next_level.append(MerkleNode(hash=parent_hash))

            current_level = next_level
            current_index //= 2

        return MerkleProof(
            leaf_hash=leaf.hash,
            leaf_index=index,
            proof_hashes=proof_hashes,
            directions=directions,
            root_hash=self._root.hash if self._root else "",
        )

    def get_leaf_hash(self, index: int) -> str:
        """Get the hash of a leaf by index."""
        if index < 0 or index >= len(self._leaves):
            raise ValueError(f"Invalid leaf index: {index}")
        return self._leaves[index].hash

    def get_all_leaf_hashes(self) -> List[str]:
        """Get all leaf hashes in order."""
        return [leaf.hash for leaf in self._leaves]


# ===========================================================================
# Verification Functions
# ===========================================================================


def verify_merkle_proof(proof: MerkleProof) -> bool:
    """
    Verify a Merkle inclusion proof.

    Args:
        proof: The proof to verify

    Returns:
        True if the proof is valid
    """
    if len(proof.proof_hashes) != len(proof.directions):
        return False

    try:
        current_hash = proof.leaf_hash

        for sibling_hash, is_left in zip(proof.proof_hashes, proof.directions):
            if is_left:
                # Sibling is on left
                current_hash = _hash_internal(sibling_hash, current_hash)
            else:
                # Sibling is on right
                current_hash = _hash_internal(current_hash, sibling_hash)

        return current_hash == proof.root_hash
    except (ValueError, TypeError):
        return False


def compute_merkle_root(leaf_hashes: List[str]) -> str:
    """
    Compute Merkle root from a list of leaf hashes.

    This is a convenience function for computing the root
    without building a full tree.

    Args:
        leaf_hashes: List of leaf hashes (already hashed with leaf prefix)

    Returns:
        Root hash
    """
    if len(leaf_hashes) == 0:
        raise ValueError("Cannot compute root with no leaves")

    if len(leaf_hashes) == 1:
        return leaf_hashes[0]

    current_level = list(leaf_hashes)

    while len(current_level) > 1:
        next_level: List[str] = []

        for i in range(0, len(current_level), 2):
            left = current_level[i]
            if i + 1 >= len(current_level):
                right = left
            else:
                right = current_level[i + 1]

            parent = _hash_internal(left, right)
            next_level.append(parent)

        current_level = next_level

    return current_level[0]


def hash_leaf_data(data: bytes) -> str:
    """
    Hash data as a Merkle leaf.

    Use this function to compute the leaf hash for verification.
    """
    return _hash_leaf(data)
