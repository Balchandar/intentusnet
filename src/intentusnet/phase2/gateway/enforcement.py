"""
Gateway Enforcement Implementation (Phase II)

The gateway is the ROOT OF TRUST in IntentusNet Phase II.

CRITICAL INVARIANTS:
1. Gateway is the ONLY entity that constructs canonical execution envelopes
2. All executions MUST be signed by the gateway
3. Encryption is MANDATORY per policy
4. Agents MUST NOT generate final execution records
5. Replay enforcement requires valid parentExecutionHash chain

This module provides:
- GatewayIdentity: Gateway's cryptographic identity
- GatewayConfig: Gateway configuration and policies
- CanonicalExecutionEnvelope: The signed, canonical execution record
- GatewayEnforcer: Main enforcement engine
- AdmissionPolicy: Policy-based admission control
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

from intentusnet.recording.models import stable_hash


# ===========================================================================
# Errors
# ===========================================================================


class GatewayEnforcementError(Exception):
    """Base error for gateway enforcement failures."""
    pass


class AdmissionDeniedError(GatewayEnforcementError):
    """Raised when an execution is denied by admission policy."""

    def __init__(self, reason: str, policy_name: str, details: Optional[Dict[str, Any]] = None):
        self.reason = reason
        self.policy_name = policy_name
        self.details = details or {}
        super().__init__(f"Admission denied by policy '{policy_name}': {reason}")


class SignatureVerificationError(GatewayEnforcementError):
    """Raised when signature verification fails."""
    pass


class ReplayViolationError(GatewayEnforcementError):
    """Raised when replay chain is violated."""
    pass


class EncryptionPolicyError(GatewayEnforcementError):
    """Raised when encryption policy is violated."""
    pass


# ===========================================================================
# Gateway Identity
# ===========================================================================


@dataclass(frozen=True)
class GatewayIdentity:
    """
    Cryptographic identity of a gateway.

    The gateway identity is the foundation of trust in Phase II.
    All canonical execution envelopes are signed with this identity.

    Attributes:
        gateway_id: Unique identifier for this gateway
        key_id: SHA-256 fingerprint of the public key (first 16 hex chars)
        public_key_bytes: Raw Ed25519 public key (32 bytes)
        domain: Optional domain name for federation
        created_at: When this identity was created
    """
    gateway_id: str
    key_id: str
    public_key_bytes: bytes
    domain: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "gatewayId": self.gateway_id,
            "keyId": self.key_id,
            "publicKey": self.public_key_bytes.hex(),
            "domain": self.domain,
            "createdAt": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GatewayIdentity":
        """Deserialize from JSON-compatible dict."""
        return cls(
            gateway_id=data["gatewayId"],
            key_id=data["keyId"],
            public_key_bytes=bytes.fromhex(data["publicKey"]),
            domain=data.get("domain"),
            created_at=data.get("createdAt", datetime.now(timezone.utc).isoformat()),
        )


# ===========================================================================
# Gateway Signature
# ===========================================================================


@dataclass(frozen=True)
class GatewaySignature:
    """
    Gateway signature over a canonical execution envelope.

    The signature covers the canonical hash of the execution,
    binding it cryptographically to the gateway's identity.

    Attributes:
        key_id: Identifier of the signing key
        signature: Ed25519 signature (64 bytes, base64 encoded)
        algorithm: Signature algorithm (always "Ed25519")
        signed_at: ISO 8601 timestamp of signature
        canonical_hash: Hash of the data that was signed
    """
    key_id: str
    signature: str  # Base64-encoded 64-byte Ed25519 signature
    algorithm: str = "Ed25519"
    signed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    canonical_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "keyId": self.key_id,
            "signature": self.signature,
            "algorithm": self.algorithm,
            "signedAt": self.signed_at,
            "canonicalHash": self.canonical_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GatewaySignature":
        """Deserialize from JSON-compatible dict."""
        return cls(
            key_id=data["keyId"],
            signature=data["signature"],
            algorithm=data.get("algorithm", "Ed25519"),
            signed_at=data.get("signedAt", datetime.now(timezone.utc).isoformat()),
            canonical_hash=data.get("canonicalHash"),
        )


# ===========================================================================
# Admission Policy
# ===========================================================================


class AdmissionDecision(Enum):
    """Result of admission policy evaluation."""
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_WITNESS = "require_witness"  # Allow but require witness attestation


@dataclass
class AdmissionResult:
    """
    Result of admission policy evaluation.

    Attributes:
        decision: The admission decision
        policy_name: Name of the policy that made the decision
        reason: Human-readable reason for the decision
        required_witnesses: Number of witnesses required (if REQUIRE_WITNESS)
        metadata: Additional policy-specific metadata
    """
    decision: AdmissionDecision
    policy_name: str
    reason: str
    required_witnesses: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class AdmissionPolicy:
    """
    Policy-based admission control for executions.

    Admission policies evaluate incoming execution requests and determine
    whether they should be allowed, denied, or require additional attestation.

    Policies are evaluated in order, and the first DENY terminates evaluation.
    """

    def __init__(self, name: str):
        self.name = name

    def evaluate(
        self,
        intent_name: str,
        payload: Dict[str, Any],
        source_agent: Optional[str],
        parent_execution_hash: Optional[str],
        context: Dict[str, Any],
    ) -> AdmissionResult:
        """
        Evaluate the admission policy.

        Args:
            intent_name: Name of the intent being executed
            payload: The intent payload
            source_agent: Agent that initiated the execution
            parent_execution_hash: Hash of parent execution (for replay)
            context: Additional context (trust domain, etc.)

        Returns:
            AdmissionResult with the policy decision
        """
        raise NotImplementedError("Subclasses must implement evaluate()")


class AllowAllPolicy(AdmissionPolicy):
    """Policy that allows all executions (for testing/development)."""

    def __init__(self):
        super().__init__("allow_all")

    def evaluate(
        self,
        intent_name: str,
        payload: Dict[str, Any],
        source_agent: Optional[str],
        parent_execution_hash: Optional[str],
        context: Dict[str, Any],
    ) -> AdmissionResult:
        return AdmissionResult(
            decision=AdmissionDecision.ALLOW,
            policy_name=self.name,
            reason="All executions allowed",
        )


class IntentAllowlistPolicy(AdmissionPolicy):
    """Policy that only allows specified intents."""

    def __init__(self, allowed_intents: Set[str]):
        super().__init__("intent_allowlist")
        self._allowed = allowed_intents

    def evaluate(
        self,
        intent_name: str,
        payload: Dict[str, Any],
        source_agent: Optional[str],
        parent_execution_hash: Optional[str],
        context: Dict[str, Any],
    ) -> AdmissionResult:
        if intent_name in self._allowed:
            return AdmissionResult(
                decision=AdmissionDecision.ALLOW,
                policy_name=self.name,
                reason=f"Intent '{intent_name}' is in allowlist",
            )
        return AdmissionResult(
            decision=AdmissionDecision.DENY,
            policy_name=self.name,
            reason=f"Intent '{intent_name}' is not in allowlist",
        )


class AgentTrustPolicy(AdmissionPolicy):
    """Policy that requires trusted source agents."""

    def __init__(self, trusted_agents: Set[str]):
        super().__init__("agent_trust")
        self._trusted = trusted_agents

    def evaluate(
        self,
        intent_name: str,
        payload: Dict[str, Any],
        source_agent: Optional[str],
        parent_execution_hash: Optional[str],
        context: Dict[str, Any],
    ) -> AdmissionResult:
        if source_agent is None:
            return AdmissionResult(
                decision=AdmissionDecision.DENY,
                policy_name=self.name,
                reason="Source agent is required",
            )
        if source_agent in self._trusted:
            return AdmissionResult(
                decision=AdmissionDecision.ALLOW,
                policy_name=self.name,
                reason=f"Agent '{source_agent}' is trusted",
            )
        return AdmissionResult(
            decision=AdmissionDecision.DENY,
            policy_name=self.name,
            reason=f"Agent '{source_agent}' is not trusted",
        )


class ReplayChainPolicy(AdmissionPolicy):
    """Policy that enforces replay chain integrity."""

    def __init__(self, require_parent_for_replays: bool = True):
        super().__init__("replay_chain")
        self._require_parent = require_parent_for_replays

    def evaluate(
        self,
        intent_name: str,
        payload: Dict[str, Any],
        source_agent: Optional[str],
        parent_execution_hash: Optional[str],
        context: Dict[str, Any],
    ) -> AdmissionResult:
        is_replay = context.get("is_replay", False)

        if is_replay and self._require_parent and parent_execution_hash is None:
            return AdmissionResult(
                decision=AdmissionDecision.DENY,
                policy_name=self.name,
                reason="Replay executions require parentExecutionHash",
            )

        return AdmissionResult(
            decision=AdmissionDecision.ALLOW,
            policy_name=self.name,
            reason="Replay chain valid or not required",
        )


class WitnessRequiredPolicy(AdmissionPolicy):
    """Policy that requires witness attestation for certain operations."""

    def __init__(
        self,
        witness_required_intents: Set[str],
        min_witnesses: int = 1,
    ):
        super().__init__("witness_required")
        self._witness_intents = witness_required_intents
        self._min_witnesses = min_witnesses

    def evaluate(
        self,
        intent_name: str,
        payload: Dict[str, Any],
        source_agent: Optional[str],
        parent_execution_hash: Optional[str],
        context: Dict[str, Any],
    ) -> AdmissionResult:
        if intent_name in self._witness_intents:
            return AdmissionResult(
                decision=AdmissionDecision.REQUIRE_WITNESS,
                policy_name=self.name,
                reason=f"Intent '{intent_name}' requires witness attestation",
                required_witnesses=self._min_witnesses,
            )
        return AdmissionResult(
            decision=AdmissionDecision.ALLOW,
            policy_name=self.name,
            reason="Witness not required",
        )


class CompositeAdmissionPolicy(AdmissionPolicy):
    """
    Composite policy that evaluates multiple policies in order.

    Evaluation rules:
    1. If any policy returns DENY, the result is DENY
    2. If any policy returns REQUIRE_WITNESS, that is accumulated
    3. Only if all policies ALLOW (with optional REQUIRE_WITNESS) is the result ALLOW
    """

    def __init__(self, policies: List[AdmissionPolicy]):
        super().__init__("composite")
        self._policies = policies

    def evaluate(
        self,
        intent_name: str,
        payload: Dict[str, Any],
        source_agent: Optional[str],
        parent_execution_hash: Optional[str],
        context: Dict[str, Any],
    ) -> AdmissionResult:
        max_witnesses = 0

        for policy in self._policies:
            result = policy.evaluate(
                intent_name, payload, source_agent, parent_execution_hash, context
            )

            if result.decision == AdmissionDecision.DENY:
                return result

            if result.decision == AdmissionDecision.REQUIRE_WITNESS:
                max_witnesses = max(max_witnesses, result.required_witnesses)

        if max_witnesses > 0:
            return AdmissionResult(
                decision=AdmissionDecision.REQUIRE_WITNESS,
                policy_name=self.name,
                reason="Witness attestation required by composite policy",
                required_witnesses=max_witnesses,
            )

        return AdmissionResult(
            decision=AdmissionDecision.ALLOW,
            policy_name=self.name,
            reason="All policies passed",
        )


# ===========================================================================
# Gateway Configuration
# ===========================================================================


@dataclass
class EncryptionRequirement(Enum):
    """Encryption requirement levels."""
    NONE = "none"  # No encryption required (development only)
    OPTIONAL = "optional"  # Encryption available but not required
    MANDATORY = "mandatory"  # All sections must be encrypted


@dataclass
class GatewayConfig:
    """
    Gateway configuration.

    Attributes:
        gateway_id: Unique identifier for this gateway
        domain: Domain name for federation discovery
        encryption_requirement: Encryption policy level
        admission_policies: List of admission policies to evaluate
        require_replay_chain: Whether replay chain must be validated
        max_payload_size_bytes: Maximum payload size
        batch_interval_seconds: Interval for Merkle batch creation
        witness_quorum_default: Default witness quorum requirement
    """
    gateway_id: str
    domain: Optional[str] = None
    encryption_requirement: str = "mandatory"  # Using str for JSON serialization
    admission_policies: List[AdmissionPolicy] = field(default_factory=list)
    require_replay_chain: bool = True
    max_payload_size_bytes: int = 10 * 1024 * 1024  # 10 MB
    batch_interval_seconds: int = 60
    witness_quorum_default: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict (excluding policies)."""
        return {
            "gatewayId": self.gateway_id,
            "domain": self.domain,
            "encryptionRequirement": self.encryption_requirement,
            "requireReplayChain": self.require_replay_chain,
            "maxPayloadSizeBytes": self.max_payload_size_bytes,
            "batchIntervalSeconds": self.batch_interval_seconds,
            "witnessQuorumDefault": self.witness_quorum_default,
        }


# ===========================================================================
# Canonical Execution Envelope
# ===========================================================================


@dataclass
class CanonicalExecutionEnvelope:
    """
    The canonical, gateway-signed execution envelope.

    This is the ONLY valid representation of an execution in Phase II.
    It is constructed EXCLUSIVELY by the gateway, never by agents.

    Attributes:
        execution_id: Unique execution identifier (UUID)
        canonical_hash: SHA-256 hash of the canonical content
        gateway_id: ID of the gateway that created this envelope
        created_at: ISO 8601 creation timestamp
        parent_execution_hash: Hash of parent execution (for replay lineage)

        intent_name: Name of the intent executed
        intent_version: Version of the intent

        input: Input payload (may be encrypted)
        output: Output payload (may be encrypted)
        trace: Execution trace (may be encrypted)
        metadata: Execution metadata

        input_encrypted: Whether input is encrypted
        output_encrypted: Whether output is encrypted
        trace_encrypted: Whether trace is encrypted

        gateway_signature: Gateway's signature over the canonical hash
        witness_attestations: List of witness attestation references

        batch_membership: Batch inclusion information (if batched)
    """
    execution_id: str
    canonical_hash: str
    gateway_id: str
    created_at: str
    parent_execution_hash: Optional[str]

    intent_name: str
    intent_version: str

    input: Dict[str, Any]
    output: Optional[Dict[str, Any]]
    trace: Optional[List[Dict[str, Any]]]
    metadata: Dict[str, Any]

    input_encrypted: bool = False
    output_encrypted: bool = False
    trace_encrypted: bool = False
    metadata_custom_encrypted: bool = False

    gateway_signature: Optional[GatewaySignature] = None
    witness_attestations: List[str] = field(default_factory=list)

    batch_membership: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        result = {
            "executionId": self.execution_id,
            "canonicalHash": self.canonical_hash,
            "gatewayId": self.gateway_id,
            "createdAt": self.created_at,
            "parentExecutionHash": self.parent_execution_hash,
            "intentName": self.intent_name,
            "intentVersion": self.intent_version,
            "input": self.input,
            "output": self.output,
            "trace": self.trace,
            "metadata": self.metadata,
            "inputEncrypted": self.input_encrypted,
            "outputEncrypted": self.output_encrypted,
            "traceEncrypted": self.trace_encrypted,
            "metadataCustomEncrypted": self.metadata_custom_encrypted,
            "gatewaySignature": self.gateway_signature.to_dict() if self.gateway_signature else None,
            "witnessAttestations": self.witness_attestations,
            "batchMembership": self.batch_membership,
        }
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CanonicalExecutionEnvelope":
        """Deserialize from JSON-compatible dict."""
        sig_data = data.get("gatewaySignature")
        signature = GatewaySignature.from_dict(sig_data) if sig_data else None

        return cls(
            execution_id=data["executionId"],
            canonical_hash=data["canonicalHash"],
            gateway_id=data["gatewayId"],
            created_at=data["createdAt"],
            parent_execution_hash=data.get("parentExecutionHash"),
            intent_name=data["intentName"],
            intent_version=data["intentVersion"],
            input=data["input"],
            output=data.get("output"),
            trace=data.get("trace"),
            metadata=data.get("metadata", {}),
            input_encrypted=data.get("inputEncrypted", False),
            output_encrypted=data.get("outputEncrypted", False),
            trace_encrypted=data.get("traceEncrypted", False),
            metadata_custom_encrypted=data.get("metadataCustomEncrypted", False),
            gateway_signature=signature,
            witness_attestations=data.get("witnessAttestations", []),
            batch_membership=data.get("batchMembership"),
        )

    def compute_canonical_hash(self) -> str:
        """
        Compute the canonical hash of this envelope.

        The hash covers all content fields but NOT the signature itself.
        """
        content = {
            "executionId": self.execution_id,
            "gatewayId": self.gateway_id,
            "createdAt": self.created_at,
            "parentExecutionHash": self.parent_execution_hash,
            "intentName": self.intent_name,
            "intentVersion": self.intent_version,
            "input": self.input,
            "output": self.output,
            "trace": self.trace,
            "metadata": self.metadata,
        }
        return stable_hash(content)

    def verify_hash(self) -> bool:
        """Verify that the canonical hash matches the content."""
        return self.canonical_hash == self.compute_canonical_hash()


# ===========================================================================
# Gateway Signer
# ===========================================================================


class GatewaySigner:
    """
    Gateway signing implementation.

    Uses Ed25519 for all signatures.
    """

    def __init__(self, private_key: Ed25519PrivateKey):
        self._private_key = private_key
        self._public_key = private_key.public_key()

        # Key ID is SHA256 of public key bytes (first 16 chars)
        public_bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        self._key_id = hashlib.sha256(public_bytes).hexdigest()[:16]
        self._public_key_bytes = public_bytes

    @property
    def key_id(self) -> str:
        return self._key_id

    @property
    def public_key_bytes(self) -> bytes:
        return self._public_key_bytes

    def sign(self, data: bytes) -> bytes:
        """Sign data with Ed25519. Returns 64-byte signature."""
        return self._private_key.sign(data)

    def create_identity(self, gateway_id: str, domain: Optional[str] = None) -> GatewayIdentity:
        """Create a gateway identity from this signer."""
        return GatewayIdentity(
            gateway_id=gateway_id,
            key_id=self._key_id,
            public_key_bytes=self._public_key_bytes,
            domain=domain,
        )

    @classmethod
    def generate(cls) -> "GatewaySigner":
        """Generate a new signing key (for testing only)."""
        private_key = Ed25519PrivateKey.generate()
        return cls(private_key)

    @classmethod
    def from_pem_file(cls, path: str, password: Optional[bytes] = None) -> "GatewaySigner":
        """Load signer from PEM-encoded private key file."""
        with open(path, "rb") as f:
            private_key = serialization.load_pem_private_key(
                f.read(),
                password=password,
            )
        if not isinstance(private_key, Ed25519PrivateKey):
            raise TypeError(f"Expected Ed25519 private key, got {type(private_key)}")
        return cls(private_key)


class GatewayVerifier:
    """
    Gateway signature verification.

    Verifies signatures using pre-loaded public keys.
    """

    def __init__(self):
        self._public_keys: Dict[str, Ed25519PublicKey] = {}
        self._identities: Dict[str, GatewayIdentity] = {}

    def add_identity(self, identity: GatewayIdentity) -> bool:
        """
        Add a gateway identity for verification.

        Returns:
            True if identity was added successfully, False if key is invalid.
        """
        if not identity.public_key_bytes or len(identity.public_key_bytes) != 32:
            # Invalid key - cannot be added for verification
            return False

        try:
            public_key = Ed25519PublicKey.from_public_bytes(identity.public_key_bytes)
            self._public_keys[identity.key_id] = public_key
            self._identities[identity.gateway_id] = identity
            return True
        except (ValueError, TypeError):
            # Invalid key format
            return False

    def add_from_signer(self, gateway_id: str, signer: GatewaySigner) -> None:
        """Add public key from a signer (for testing)."""
        identity = signer.create_identity(gateway_id)
        self.add_identity(identity)

    def verify(self, data: bytes, signature: bytes, key_id: str) -> bool:
        """Verify a signature."""
        if key_id not in self._public_keys:
            return False

        try:
            self._public_keys[key_id].verify(signature, data)
            return True
        except InvalidSignature:
            return False

    def verify_envelope(self, envelope: CanonicalExecutionEnvelope) -> bool:
        """
        Verify a canonical execution envelope.

        Checks:
        1. Canonical hash matches content
        2. Gateway signature is valid
        """
        if not envelope.verify_hash():
            return False

        if envelope.gateway_signature is None:
            return False

        import base64
        signature_bytes = base64.b64decode(envelope.gateway_signature.signature)
        data = envelope.canonical_hash.encode("utf-8")

        return self.verify(data, signature_bytes, envelope.gateway_signature.key_id)

    def get_identity(self, gateway_id: str) -> Optional[GatewayIdentity]:
        """Get a gateway identity by gateway ID."""
        return self._identities.get(gateway_id)

    def has_key(self, key_id: str) -> bool:
        """Check if a key is registered."""
        return key_id in self._public_keys


# ===========================================================================
# Gateway Enforcer
# ===========================================================================


class GatewayEnforcer:
    """
    Main gateway enforcement engine.

    The GatewayEnforcer is responsible for:
    1. Evaluating admission policies
    2. Constructing canonical execution envelopes
    3. Signing executions with the gateway key
    4. Enforcing encryption policies
    5. Validating replay chains

    CRITICAL: This is the ONLY component that creates canonical execution envelopes.
    Agents MUST NOT create execution records directly.
    """

    def __init__(
        self,
        config: GatewayConfig,
        signer: GatewaySigner,
        verifier: Optional[GatewayVerifier] = None,
    ):
        self._config = config
        self._signer = signer
        self._verifier = verifier or GatewayVerifier()

        # Create identity and add to verifier
        self._identity = signer.create_identity(config.gateway_id, config.domain)
        self._verifier.add_identity(self._identity)

        # Build composite policy
        self._admission_policy = CompositeAdmissionPolicy(
            config.admission_policies if config.admission_policies else [AllowAllPolicy()]
        )

        # Execution tracking for replay chain
        self._execution_hashes: Dict[str, str] = {}

    @property
    def identity(self) -> GatewayIdentity:
        return self._identity

    @property
    def config(self) -> GatewayConfig:
        return self._config

    @property
    def verifier(self) -> GatewayVerifier:
        return self._verifier

    def evaluate_admission(
        self,
        intent_name: str,
        payload: Dict[str, Any],
        source_agent: Optional[str] = None,
        parent_execution_hash: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AdmissionResult:
        """
        Evaluate admission policies for an execution request.

        Returns:
            AdmissionResult with the policy decision

        Raises:
            AdmissionDeniedError: If the execution is denied
        """
        ctx = context or {}
        result = self._admission_policy.evaluate(
            intent_name, payload, source_agent, parent_execution_hash, ctx
        )

        if result.decision == AdmissionDecision.DENY:
            raise AdmissionDeniedError(
                reason=result.reason,
                policy_name=result.policy_name,
                details=result.metadata,
            )

        return result

    def validate_replay_chain(
        self,
        parent_execution_hash: Optional[str],
    ) -> None:
        """
        Validate replay chain integrity.

        Raises:
            ReplayViolationError: If the replay chain is invalid
        """
        if not self._config.require_replay_chain:
            return

        if parent_execution_hash is not None:
            # Verify the parent exists and hash matches
            if parent_execution_hash not in self._execution_hashes:
                # In production, this would query a store
                # For now, we just validate format
                if len(parent_execution_hash) != 64:
                    raise ReplayViolationError(
                        f"Invalid parent execution hash format: {parent_execution_hash}"
                    )

    def enforce_encryption_policy(
        self,
        input_encrypted: bool,
        output_encrypted: bool,
        trace_encrypted: bool,
    ) -> None:
        """
        Enforce encryption policy.

        Raises:
            EncryptionPolicyError: If encryption policy is violated
        """
        if self._config.encryption_requirement == "mandatory":
            if not input_encrypted:
                raise EncryptionPolicyError("Input encryption is mandatory")
            if not output_encrypted:
                raise EncryptionPolicyError("Output encryption is mandatory")
            if not trace_encrypted:
                raise EncryptionPolicyError("Trace encryption is mandatory")

    def construct_envelope(
        self,
        intent_name: str,
        intent_version: str,
        input_payload: Dict[str, Any],
        output_payload: Optional[Dict[str, Any]],
        trace: Optional[List[Dict[str, Any]]],
        metadata: Dict[str, Any],
        parent_execution_hash: Optional[str] = None,
        input_encrypted: bool = False,
        output_encrypted: bool = False,
        trace_encrypted: bool = False,
        metadata_custom_encrypted: bool = False,
        execution_id: Optional[str] = None,
    ) -> CanonicalExecutionEnvelope:
        """
        Construct a canonical execution envelope.

        This is the ONLY method that should create CanonicalExecutionEnvelope instances.
        Agents MUST NOT construct these directly.

        Args:
            intent_name: Name of the intent
            intent_version: Version of the intent
            input_payload: Input (may be encrypted envelope)
            output_payload: Output (may be encrypted envelope)
            trace: Execution trace (may be encrypted)
            metadata: Execution metadata
            parent_execution_hash: Parent execution for replay lineage
            input_encrypted: Whether input is encrypted
            output_encrypted: Whether output is encrypted
            trace_encrypted: Whether trace is encrypted
            metadata_custom_encrypted: Whether metadata.custom is encrypted
            execution_id: Optional explicit execution ID

        Returns:
            Signed CanonicalExecutionEnvelope

        Raises:
            EncryptionPolicyError: If encryption policy is violated
            ReplayViolationError: If replay chain is invalid
        """
        # Validate replay chain
        self.validate_replay_chain(parent_execution_hash)

        # Enforce encryption policy
        self.enforce_encryption_policy(input_encrypted, output_encrypted, trace_encrypted)

        # Generate execution ID
        exec_id = execution_id or str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        # Create unsigned envelope
        envelope = CanonicalExecutionEnvelope(
            execution_id=exec_id,
            canonical_hash="",  # Will be computed
            gateway_id=self._config.gateway_id,
            created_at=created_at,
            parent_execution_hash=parent_execution_hash,
            intent_name=intent_name,
            intent_version=intent_version,
            input=input_payload,
            output=output_payload,
            trace=trace,
            metadata=metadata,
            input_encrypted=input_encrypted,
            output_encrypted=output_encrypted,
            trace_encrypted=trace_encrypted,
            metadata_custom_encrypted=metadata_custom_encrypted,
        )

        # Compute canonical hash
        canonical_hash = envelope.compute_canonical_hash()
        envelope.canonical_hash = canonical_hash

        # Sign the envelope
        signature = self._sign_envelope(envelope)
        envelope.gateway_signature = signature

        # Track execution hash for replay chain
        self._execution_hashes[exec_id] = canonical_hash

        return envelope

    def _sign_envelope(self, envelope: CanonicalExecutionEnvelope) -> GatewaySignature:
        """Sign the canonical hash of an envelope."""
        import base64

        data = envelope.canonical_hash.encode("utf-8")
        signature_bytes = self._signer.sign(data)

        return GatewaySignature(
            key_id=self._signer.key_id,
            signature=base64.b64encode(signature_bytes).decode("ascii"),
            algorithm="Ed25519",
            signed_at=datetime.now(timezone.utc).isoformat(),
            canonical_hash=envelope.canonical_hash,
        )

    def verify_envelope(self, envelope: CanonicalExecutionEnvelope) -> bool:
        """
        Verify a canonical execution envelope.

        CRITICAL: Signature MUST verify before ANY content is trusted.
        """
        return self._verifier.verify_envelope(envelope)

    def add_foreign_gateway(self, identity: GatewayIdentity) -> None:
        """
        Add a foreign gateway identity for cross-gateway verification.

        This enables verification of executions from federated gateways.
        """
        self._verifier.add_identity(identity)
