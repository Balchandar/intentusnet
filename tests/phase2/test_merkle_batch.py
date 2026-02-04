"""
Tests for Merkle-Rooted Execution Batches (Phase II)
"""

import pytest
from intentusnet.phase2.merkle.tree import (
    MerkleTree,
    MerkleProof,
    verify_merkle_proof,
    compute_merkle_root,
    hash_leaf_data,
)
from intentusnet.phase2.merkle.batch import (
    ExecutionBatch,
    BatchLeaf,
    BatchRoot,
    BatchInclusionProof,
    BatchBuilder,
    BatchVerifier,
)
from intentusnet.phase2.gateway.enforcement import (
    GatewaySigner,
    GatewayConfig,
    GatewayEnforcer,
)


class TestMerkleTree:
    """Tests for MerkleTree."""

    def test_single_leaf(self):
        """Test tree with single leaf."""
        tree = MerkleTree()
        tree.add_leaf(b"leaf1")
        root = tree.build()

        assert root is not None
        assert tree.leaf_count == 1

    def test_multiple_leaves(self):
        """Test tree with multiple leaves."""
        tree = MerkleTree()
        for i in range(4):
            tree.add_leaf(f"leaf{i}".encode())

        root = tree.build()

        assert root is not None
        assert tree.leaf_count == 4

    def test_odd_number_of_leaves(self):
        """Test tree with odd number of leaves."""
        tree = MerkleTree()
        for i in range(5):
            tree.add_leaf(f"leaf{i}".encode())

        root = tree.build()

        assert root is not None
        assert tree.leaf_count == 5

    def test_inclusion_proof_valid(self):
        """Test inclusion proof verification."""
        tree = MerkleTree()
        for i in range(8):
            tree.add_leaf(f"leaf{i}".encode())

        tree.build()

        # Get proof for each leaf
        for i in range(8):
            proof = tree.get_proof(i)
            assert verify_merkle_proof(proof)

    def test_inclusion_proof_invalid_on_tampered_leaf(self):
        """Test proof fails with tampered leaf hash."""
        tree = MerkleTree()
        for i in range(4):
            tree.add_leaf(f"leaf{i}".encode())

        tree.build()
        proof = tree.get_proof(0)

        # Tamper with leaf hash
        proof.leaf_hash = "invalid" + proof.leaf_hash[7:]

        assert not verify_merkle_proof(proof)

    def test_deterministic_root(self):
        """Test that same leaves produce same root."""
        leaves = [f"leaf{i}".encode() for i in range(4)]

        tree1 = MerkleTree()
        tree2 = MerkleTree()

        for leaf in leaves:
            tree1.add_leaf(leaf)
            tree2.add_leaf(leaf)

        root1 = tree1.build()
        root2 = tree2.build()

        assert root1 == root2

    def test_compute_merkle_root_matches_tree(self):
        """Test compute_merkle_root matches tree root."""
        tree = MerkleTree()
        leaf_hashes = []

        for i in range(4):
            data = f"leaf{i}".encode()
            tree.add_leaf(data)
            leaf_hashes.append(hash_leaf_data(data))

        tree_root = tree.build()
        computed_root = compute_merkle_root(leaf_hashes)

        assert tree_root == computed_root


class TestBatchBuilder:
    """Tests for BatchBuilder."""

    @pytest.fixture
    def signer(self):
        """Create a signer for testing."""
        return GatewaySigner.generate()

    @pytest.fixture
    def enforcer(self, signer):
        """Create an enforcer for testing."""
        config = GatewayConfig(gateway_id="test-gateway", encryption_requirement="optional")
        return GatewayEnforcer(config, signer)

    def test_build_empty_batch_fails(self, signer):
        """Test that building empty batch fails."""
        builder = BatchBuilder("test-gateway")

        with pytest.raises(ValueError):
            builder.build_and_seal(signer)

    def test_build_batch_with_single_execution(self, signer, enforcer):
        """Test building batch with single execution."""
        builder = BatchBuilder("test-gateway")

        envelope = enforcer.construct_envelope(
            intent_name="process",
            intent_version="1.0",
            input_payload={},
            output_payload=None,
            trace=None,
            metadata={},
        )

        builder.add_execution(envelope)
        batch = builder.build_and_seal(signer)

        assert batch.sealed
        assert batch.root is not None
        assert len(batch.leaves) == 1

    def test_build_batch_with_multiple_executions(self, signer, enforcer):
        """Test building batch with multiple executions."""
        builder = BatchBuilder("test-gateway")

        for i in range(5):
            envelope = enforcer.construct_envelope(
                intent_name=f"process_{i}",
                intent_version="1.0",
                input_payload={"index": i},
                output_payload=None,
                trace=None,
                metadata={},
            )
            builder.add_execution(envelope)

        batch = builder.build_and_seal(signer)

        assert batch.sealed
        assert len(batch.leaves) == 5
        assert batch.root.leaf_count == 5

    def test_batch_inclusion_proof(self, signer, enforcer):
        """Test getting inclusion proof from batch."""
        builder = BatchBuilder("test-gateway")

        envelopes = []
        for i in range(4):
            envelope = enforcer.construct_envelope(
                intent_name=f"process_{i}",
                intent_version="1.0",
                input_payload={"index": i},
                output_payload=None,
                trace=None,
                metadata={},
            )
            builder.add_execution(envelope)
            envelopes.append(envelope)

        batch = builder.build_and_seal(signer)

        # Get and verify proof for each execution
        for envelope in envelopes:
            proof = batch.get_inclusion_proof(envelope.execution_id)
            assert proof is not None
            assert proof.verify()

    def test_leaves_sorted_by_execution_id(self, signer, enforcer):
        """Test that leaves are sorted by execution ID."""
        builder = BatchBuilder("test-gateway")

        for i in range(10):
            envelope = enforcer.construct_envelope(
                intent_name=f"process_{i}",
                intent_version="1.0",
                input_payload={"index": i},
                output_payload=None,
                trace=None,
                metadata={},
            )
            builder.add_execution(envelope)

        batch = builder.build_and_seal(signer)

        # Verify leaves are sorted
        execution_ids = [leaf.execution_id for leaf in batch.leaves]
        assert execution_ids == sorted(execution_ids)

    def test_duplicate_execution_rejected(self, signer, enforcer):
        """Test that duplicate executions are rejected."""
        builder = BatchBuilder("test-gateway")

        envelope = enforcer.construct_envelope(
            intent_name="process",
            intent_version="1.0",
            input_payload={},
            output_payload=None,
            trace=None,
            metadata={},
        )

        builder.add_execution(envelope)

        with pytest.raises(ValueError):
            builder.add_execution(envelope)


class TestBatchVerifier:
    """Tests for BatchVerifier."""

    @pytest.fixture
    def signer(self):
        """Create a signer for testing."""
        return GatewaySigner.generate()

    @pytest.fixture
    def enforcer(self, signer):
        """Create an enforcer for testing."""
        config = GatewayConfig(gateway_id="test-gateway", encryption_requirement="optional")
        return GatewayEnforcer(config, signer)

    @pytest.fixture
    def batch(self, signer, enforcer):
        """Create a batch for testing."""
        builder = BatchBuilder("test-gateway")

        for i in range(4):
            envelope = enforcer.construct_envelope(
                intent_name=f"process_{i}",
                intent_version="1.0",
                input_payload={"index": i},
                output_payload=None,
                trace=None,
                metadata={},
            )
            builder.add_execution(envelope)

        return builder.build_and_seal(signer)

    def test_verify_batch_signature(self, signer, batch):
        """Test verifying batch signature."""
        verifier = BatchVerifier({signer.key_id: signer.public_key_bytes})

        assert verifier.verify_batch_signature(batch)

    def test_verify_batch_signature_unknown_key(self, batch):
        """Test verification fails with unknown key."""
        verifier = BatchVerifier({})

        assert not verifier.verify_batch_signature(batch)

    def test_verify_inclusion_proof(self, signer, batch):
        """Test verifying inclusion proof."""
        verifier = BatchVerifier({signer.key_id: signer.public_key_bytes})

        proof = batch.get_inclusion_proof(batch.leaves[0].execution_id)
        assert verifier.verify_inclusion_proof(proof)

    def test_verify_batch_consistency(self, signer, batch):
        """Test verifying batch internal consistency."""
        verifier = BatchVerifier({signer.key_id: signer.public_key_bytes})

        assert verifier.verify_batch_consistency(batch)


class TestBatchSerialization:
    """Tests for batch serialization."""

    @pytest.fixture
    def signer(self):
        """Create a signer for testing."""
        return GatewaySigner.generate()

    @pytest.fixture
    def enforcer(self, signer):
        """Create an enforcer for testing."""
        config = GatewayConfig(gateway_id="test-gateway", encryption_requirement="optional")
        return GatewayEnforcer(config, signer)

    def test_batch_serialization_roundtrip(self, signer, enforcer):
        """Test batch serialization and deserialization."""
        builder = BatchBuilder("test-gateway")

        for i in range(3):
            envelope = enforcer.construct_envelope(
                intent_name=f"process_{i}",
                intent_version="1.0",
                input_payload={"index": i},
                output_payload=None,
                trace=None,
                metadata={},
            )
            builder.add_execution(envelope)

        original = builder.build_and_seal(signer)

        # Serialize
        data = original.to_dict()

        # Deserialize
        restored = ExecutionBatch.from_dict(data)

        assert restored.batch_id == original.batch_id
        assert restored.gateway_id == original.gateway_id
        assert len(restored.leaves) == len(original.leaves)
        assert restored.root.root_hash == original.root.root_hash
