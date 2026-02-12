"""
Tests for Gateway Enforcement (Phase II)
"""

import pytest
from intentusnet.phase2.gateway.enforcement import (
    GatewayEnforcer,
    GatewayConfig,
    GatewaySigner,
    GatewayVerifier,
    GatewayIdentity,
    CanonicalExecutionEnvelope,
    GatewaySignature,
    AdmissionPolicy,
    AdmissionResult,
    AdmissionDecision,
    AdmissionDeniedError,
    AllowAllPolicy,
    IntentAllowlistPolicy,
    AgentTrustPolicy,
    ReplayChainPolicy,
    CompositeAdmissionPolicy,
)


class TestGatewaySigner:
    """Tests for GatewaySigner."""

    def test_generate_signer(self):
        """Test generating a new signer."""
        signer = GatewaySigner.generate()
        assert signer.key_id is not None
        assert len(signer.key_id) == 16
        assert len(signer.public_key_bytes) == 32

    def test_sign_and_verify(self):
        """Test signing and verification."""
        signer = GatewaySigner.generate()
        data = b"test data to sign"

        signature = signer.sign(data)
        assert len(signature) == 64  # Ed25519 signature

        # Verify with public key
        verifier = GatewayVerifier()
        verifier.add_from_signer("test-gateway", signer)

        assert verifier.verify(data, signature, signer.key_id)

    def test_create_identity(self):
        """Test creating gateway identity from signer."""
        signer = GatewaySigner.generate()
        identity = signer.create_identity("gateway-001", "example.com")

        assert identity.gateway_id == "gateway-001"
        assert identity.domain == "example.com"
        assert identity.key_id == signer.key_id
        assert identity.public_key_bytes == signer.public_key_bytes


class TestGatewayVerifier:
    """Tests for GatewayVerifier."""

    def test_add_and_verify(self):
        """Test adding identity and verifying."""
        signer = GatewaySigner.generate()
        verifier = GatewayVerifier()

        identity = signer.create_identity("gateway-001")
        verifier.add_identity(identity)

        assert verifier.has_key(signer.key_id)
        assert verifier.get_identity("gateway-001") is not None

    def test_verify_invalid_signature(self):
        """Test verification fails with invalid signature."""
        signer = GatewaySigner.generate()
        verifier = GatewayVerifier()
        verifier.add_from_signer("test-gateway", signer)

        data = b"test data"
        invalid_signature = b"\x00" * 64

        assert not verifier.verify(data, invalid_signature, signer.key_id)

    def test_verify_unknown_key(self):
        """Test verification fails with unknown key."""
        verifier = GatewayVerifier()
        data = b"test data"
        signature = b"\x00" * 64

        assert not verifier.verify(data, signature, "unknown-key")


class TestAdmissionPolicies:
    """Tests for admission policies."""

    def test_allow_all_policy(self):
        """Test AllowAllPolicy allows everything."""
        policy = AllowAllPolicy()
        result = policy.evaluate("any_intent", {}, "any_agent", None, {})

        assert result.decision == AdmissionDecision.ALLOW

    def test_intent_allowlist_policy_allowed(self):
        """Test IntentAllowlistPolicy allows listed intents."""
        policy = IntentAllowlistPolicy({"process", "query"})
        result = policy.evaluate("process", {}, "agent", None, {})

        assert result.decision == AdmissionDecision.ALLOW

    def test_intent_allowlist_policy_denied(self):
        """Test IntentAllowlistPolicy denies unlisted intents."""
        policy = IntentAllowlistPolicy({"process", "query"})
        result = policy.evaluate("delete", {}, "agent", None, {})

        assert result.decision == AdmissionDecision.DENY

    def test_agent_trust_policy_trusted(self):
        """Test AgentTrustPolicy allows trusted agents."""
        policy = AgentTrustPolicy({"agent-001", "agent-002"})
        result = policy.evaluate("intent", {}, "agent-001", None, {})

        assert result.decision == AdmissionDecision.ALLOW

    def test_agent_trust_policy_untrusted(self):
        """Test AgentTrustPolicy denies untrusted agents."""
        policy = AgentTrustPolicy({"agent-001"})
        result = policy.evaluate("intent", {}, "agent-003", None, {})

        assert result.decision == AdmissionDecision.DENY

    def test_replay_chain_policy_requires_parent(self):
        """Test ReplayChainPolicy requires parent for replays."""
        policy = ReplayChainPolicy(require_parent_for_replays=True)

        # Non-replay allowed without parent
        result = policy.evaluate("intent", {}, "agent", None, {"is_replay": False})
        assert result.decision == AdmissionDecision.ALLOW

        # Replay without parent denied
        result = policy.evaluate("intent", {}, "agent", None, {"is_replay": True})
        assert result.decision == AdmissionDecision.DENY

        # Replay with parent allowed
        result = policy.evaluate("intent", {}, "agent", "abc" * 21 + "d", {"is_replay": True})
        assert result.decision == AdmissionDecision.ALLOW

    def test_composite_policy_denies_on_first_deny(self):
        """Test CompositeAdmissionPolicy stops on first deny."""
        policy = CompositeAdmissionPolicy([
            AllowAllPolicy(),
            IntentAllowlistPolicy({"allowed"}),
            AllowAllPolicy(),
        ])

        result = policy.evaluate("not_allowed", {}, "agent", None, {})
        assert result.decision == AdmissionDecision.DENY


class TestGatewayEnforcer:
    """Tests for GatewayEnforcer."""

    @pytest.fixture
    def enforcer(self):
        """Create a gateway enforcer for testing."""
        signer = GatewaySigner.generate()
        config = GatewayConfig(
            gateway_id="test-gateway",
            encryption_requirement="optional",
        )
        return GatewayEnforcer(config, signer)

    def test_construct_envelope(self, enforcer):
        """Test constructing a canonical envelope."""
        envelope = enforcer.construct_envelope(
            intent_name="process",
            intent_version="1.0",
            input_payload={"key": "value"},
            output_payload={"result": "success"},
            trace=[{"type": "step", "name": "process"}],
            metadata={"agent": "test"},
        )

        assert envelope.execution_id is not None
        assert envelope.canonical_hash is not None
        assert envelope.gateway_id == "test-gateway"
        assert envelope.intent_name == "process"
        assert envelope.gateway_signature is not None

    def test_verify_envelope(self, enforcer):
        """Test verifying a constructed envelope."""
        envelope = enforcer.construct_envelope(
            intent_name="process",
            intent_version="1.0",
            input_payload={"key": "value"},
            output_payload=None,
            trace=None,
            metadata={},
        )

        assert enforcer.verify_envelope(envelope)

    def test_envelope_hash_verification(self, enforcer):
        """Test that envelope hash verification works."""
        envelope = enforcer.construct_envelope(
            intent_name="process",
            intent_version="1.0",
            input_payload={"key": "value"},
            output_payload=None,
            trace=None,
            metadata={},
        )

        assert envelope.verify_hash()

        # Tamper with content
        envelope.input["key"] = "tampered"
        assert not envelope.verify_hash()

    def test_admission_policy_enforcement(self):
        """Test that admission policies are enforced."""
        signer = GatewaySigner.generate()
        config = GatewayConfig(
            gateway_id="test-gateway",
            encryption_requirement="optional",
            admission_policies=[IntentAllowlistPolicy({"allowed"})],
        )
        enforcer = GatewayEnforcer(config, signer)

        # Allowed intent passes
        result = enforcer.evaluate_admission("allowed", {})
        assert result.decision == AdmissionDecision.ALLOW

        # Denied intent raises
        with pytest.raises(AdmissionDeniedError):
            enforcer.evaluate_admission("denied", {})

    def test_cross_gateway_verification(self):
        """Test verification of envelope from different gateway."""
        # Create envelope with first gateway
        signer1 = GatewaySigner.generate()
        config1 = GatewayConfig(gateway_id="gateway-1", encryption_requirement="optional")
        enforcer1 = GatewayEnforcer(config1, signer1)

        envelope = enforcer1.construct_envelope(
            intent_name="process",
            intent_version="1.0",
            input_payload={},
            output_payload=None,
            trace=None,
            metadata={},
        )

        # Create second gateway and add first gateway's identity
        signer2 = GatewaySigner.generate()
        config2 = GatewayConfig(gateway_id="gateway-2", encryption_requirement="optional")
        enforcer2 = GatewayEnforcer(config2, signer2)

        # Add first gateway's identity for verification
        enforcer2.add_foreign_gateway(enforcer1.identity)

        # Second gateway can verify first gateway's envelope
        assert enforcer2.verify_envelope(envelope)


class TestCanonicalExecutionEnvelope:
    """Tests for CanonicalExecutionEnvelope."""

    def test_serialization_roundtrip(self):
        """Test envelope serialization and deserialization."""
        signer = GatewaySigner.generate()
        config = GatewayConfig(gateway_id="test", encryption_requirement="optional")
        enforcer = GatewayEnforcer(config, signer)

        original = enforcer.construct_envelope(
            intent_name="process",
            intent_version="1.0",
            input_payload={"key": "value"},
            output_payload={"result": "success"},
            trace=[{"type": "step"}],
            metadata={"agent": "test"},
        )

        # Serialize
        data = original.to_dict()

        # Deserialize
        restored = CanonicalExecutionEnvelope.from_dict(data)

        assert restored.execution_id == original.execution_id
        assert restored.canonical_hash == original.canonical_hash
        assert restored.gateway_id == original.gateway_id
        assert restored.intent_name == original.intent_name

    def test_compute_canonical_hash(self):
        """Test canonical hash computation is deterministic."""
        signer = GatewaySigner.generate()
        config = GatewayConfig(gateway_id="test", encryption_requirement="optional")
        enforcer = GatewayEnforcer(config, signer)

        envelope = enforcer.construct_envelope(
            intent_name="process",
            intent_version="1.0",
            input_payload={"key": "value"},
            output_payload=None,
            trace=None,
            metadata={},
        )

        # Compute hash multiple times
        hash1 = envelope.compute_canonical_hash()
        hash2 = envelope.compute_canonical_hash()

        assert hash1 == hash2
        assert hash1 == envelope.canonical_hash
