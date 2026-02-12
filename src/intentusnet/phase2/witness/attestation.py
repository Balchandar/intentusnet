"""
Witness Gateway Implementation (Phase II)

Witness gateways provide independent verification of executions
without the ability to create new executions.

Key concepts:
- Witness-only role (no execution creation)
- Deterministic verification only (no decryption)
- Witness attestation records
- Multi-witness quorum enforcement
- Gateway policy enforcement using witness attestations

CRITICAL INVARIANTS:
1. Witness gateways NEVER create executions
2. Witness gateways NEVER decrypt payloads
3. Verification is deterministic and reproducible
4. Quorum requirements are enforced before acceptance
"""

from __future__ import annotations

import base64
import hashlib
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

from intentusnet.phase2.gateway.enforcement import (
    CanonicalExecutionEnvelope,
)


# ===========================================================================
# Witness Role
# ===========================================================================


class WitnessRole(Enum):
    """Role of a witness gateway."""
    FULL_WITNESS = "full_witness"  # Full verification capability
    HASH_WITNESS = "hash_witness"  # Hash verification only
    SIGNATURE_WITNESS = "signature_witness"  # Signature verification only


# ===========================================================================
# Witness Scope
# ===========================================================================


class WitnessScope(Enum):
    """Scope of what a witness verifies."""
    CANONICAL_HASH = "canonical_hash"  # Verifies canonical hash matches content
    GATEWAY_SIGNATURE = "gateway_signature"  # Verifies gateway signature
    LINEAGE = "lineage"  # Verifies parent execution lineage
    BATCH_MEMBERSHIP = "batch_membership"  # Verifies batch inclusion
    TRANSPARENCY = "transparency"  # Verifies transparency log inclusion


# ===========================================================================
# Witness Identity
# ===========================================================================


@dataclass(frozen=True)
class WitnessIdentity:
    """
    Identity of a witness gateway.

    Attributes:
        witness_id: Unique identifier for this witness
        key_id: SHA-256 fingerprint of the public key
        public_key_bytes: Raw Ed25519 public key
        role: Role of this witness
        supported_scopes: Verification scopes this witness supports
        domain: Optional domain name
    """
    witness_id: str
    key_id: str
    public_key_bytes: bytes
    role: WitnessRole
    supported_scopes: Set[WitnessScope]
    domain: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "witnessId": self.witness_id,
            "keyId": self.key_id,
            "publicKey": self.public_key_bytes.hex(),
            "role": self.role.value,
            "supportedScopes": [s.value for s in self.supported_scopes],
            "domain": self.domain,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WitnessIdentity":
        return cls(
            witness_id=data["witnessId"],
            key_id=data["keyId"],
            public_key_bytes=bytes.fromhex(data["publicKey"]),
            role=WitnessRole(data["role"]),
            supported_scopes={WitnessScope(s) for s in data["supportedScopes"]},
            domain=data.get("domain"),
        )


# ===========================================================================
# Witness Attestation
# ===========================================================================


class AttestationStatus(Enum):
    """Status of a witness attestation."""
    VALID = "valid"  # Verification passed
    INVALID = "invalid"  # Verification failed
    PARTIAL = "partial"  # Some scopes passed, some failed


@dataclass
class WitnessAttestation:
    """
    Attestation from a witness gateway.

    A witness attestation is a signed statement that a witness has
    verified specific aspects of an execution.

    Attributes:
        attestation_id: Unique identifier for this attestation
        witness_id: ID of the attesting witness
        execution_id: ID of the execution being attested
        canonical_hash: Hash of the execution
        scopes_verified: Which verification scopes were checked
        scope_results: Results for each scope
        status: Overall attestation status
        signature: Witness signature over the attestation
        key_id: Key ID used for signing
        created_at: When the attestation was created
    """
    attestation_id: str
    witness_id: str
    execution_id: str
    canonical_hash: str
    scopes_verified: List[WitnessScope]
    scope_results: Dict[str, bool]
    status: AttestationStatus
    signature: str  # Base64-encoded Ed25519 signature
    key_id: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attestationId": self.attestation_id,
            "witnessId": self.witness_id,
            "executionId": self.execution_id,
            "canonicalHash": self.canonical_hash,
            "scopesVerified": [s.value for s in self.scopes_verified],
            "scopeResults": self.scope_results,
            "status": self.status.value,
            "signature": self.signature,
            "keyId": self.key_id,
            "createdAt": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WitnessAttestation":
        return cls(
            attestation_id=data["attestationId"],
            witness_id=data["witnessId"],
            execution_id=data["executionId"],
            canonical_hash=data["canonicalHash"],
            scopes_verified=[WitnessScope(s) for s in data["scopesVerified"]],
            scope_results=data["scopeResults"],
            status=AttestationStatus(data["status"]),
            signature=data["signature"],
            key_id=data["keyId"],
            created_at=data.get("createdAt", datetime.now(timezone.utc).isoformat()),
        )

    def compute_attestation_hash(self) -> str:
        """Compute hash of attestation content (excluding signature)."""
        import json

        content = {
            "attestationId": self.attestation_id,
            "witnessId": self.witness_id,
            "executionId": self.execution_id,
            "canonicalHash": self.canonical_hash,
            "scopesVerified": sorted([s.value for s in self.scopes_verified]),
            "scopeResults": dict(sorted(self.scope_results.items())),
            "status": self.status.value,
            "createdAt": self.created_at,
        }
        canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ===========================================================================
# Quorum State
# ===========================================================================


class QuorumState(Enum):
    """State of witness quorum."""
    NOT_MET = "not_met"  # Quorum not yet reached
    MET = "met"  # Quorum reached
    FAILED = "failed"  # Cannot reach quorum (too many failures)


@dataclass
class WitnessQuorum:
    """
    Tracks witness attestations for quorum enforcement.

    Attributes:
        execution_id: ID of the execution
        canonical_hash: Hash of the execution
        required_witnesses: Minimum witnesses required
        required_scopes: Scopes that must be verified
        attestations: Collected attestations
        state: Current quorum state
    """
    execution_id: str
    canonical_hash: str
    required_witnesses: int
    required_scopes: Set[WitnessScope]
    attestations: List[WitnessAttestation] = field(default_factory=list)
    state: QuorumState = QuorumState.NOT_MET

    def to_dict(self) -> Dict[str, Any]:
        return {
            "executionId": self.execution_id,
            "canonicalHash": self.canonical_hash,
            "requiredWitnesses": self.required_witnesses,
            "requiredScopes": [s.value for s in self.required_scopes],
            "attestations": [a.to_dict() for a in self.attestations],
            "state": self.state.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WitnessQuorum":
        return cls(
            execution_id=data["executionId"],
            canonical_hash=data["canonicalHash"],
            required_witnesses=data["requiredWitnesses"],
            required_scopes={WitnessScope(s) for s in data["requiredScopes"]},
            attestations=[
                WitnessAttestation.from_dict(a)
                for a in data.get("attestations", [])
            ],
            state=QuorumState(data.get("state", "not_met")),
        )

    def add_attestation(self, attestation: WitnessAttestation) -> None:
        """Add an attestation to the quorum."""
        if attestation.canonical_hash != self.canonical_hash:
            raise ValueError("Attestation hash does not match quorum hash")

        # Check for duplicate witness
        for existing in self.attestations:
            if existing.witness_id == attestation.witness_id:
                raise ValueError(f"Witness {attestation.witness_id} already attested")

        self.attestations.append(attestation)
        self._update_state()

    def _update_state(self) -> None:
        """Update quorum state based on current attestations."""
        valid_attestations = [
            a for a in self.attestations
            if a.status in (AttestationStatus.VALID, AttestationStatus.PARTIAL)
        ]

        if len(valid_attestations) >= self.required_witnesses:
            # Check if all required scopes are covered
            covered_scopes: Set[WitnessScope] = set()
            for attestation in valid_attestations:
                for scope in attestation.scopes_verified:
                    if attestation.scope_results.get(scope.value, False):
                        covered_scopes.add(scope)

            if self.required_scopes.issubset(covered_scopes):
                self.state = QuorumState.MET
            else:
                self.state = QuorumState.NOT_MET
        else:
            self.state = QuorumState.NOT_MET

    def get_valid_witnesses(self) -> List[str]:
        """Get IDs of witnesses with valid attestations."""
        return [
            a.witness_id for a in self.attestations
            if a.status == AttestationStatus.VALID
        ]

    def get_missing_scopes(self) -> Set[WitnessScope]:
        """Get scopes that have not been verified by any witness."""
        covered: Set[WitnessScope] = set()
        for attestation in self.attestations:
            if attestation.status == AttestationStatus.VALID:
                for scope in attestation.scopes_verified:
                    if attestation.scope_results.get(scope.value, False):
                        covered.add(scope)
        return self.required_scopes - covered


# ===========================================================================
# Witness Quorum Policy
# ===========================================================================


@dataclass
class WitnessQuorumPolicy:
    """
    Policy for witness quorum requirements.

    Attributes:
        policy_id: Unique identifier for this policy
        name: Human-readable name
        default_witness_count: Default required witness count
        default_scopes: Default required verification scopes
        intent_overrides: Per-intent override configurations
        max_attestation_age_seconds: Max age for attestations
    """
    policy_id: str
    name: str
    default_witness_count: int = 1
    default_scopes: Set[WitnessScope] = field(
        default_factory=lambda: {WitnessScope.CANONICAL_HASH, WitnessScope.GATEWAY_SIGNATURE}
    )
    intent_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    max_attestation_age_seconds: int = 3600

    def get_requirements(self, intent_name: str) -> tuple[int, Set[WitnessScope]]:
        """Get witness requirements for an intent."""
        override = self.intent_overrides.get(intent_name)
        if override:
            count = override.get("witness_count", self.default_witness_count)
            scopes = {WitnessScope(s) for s in override.get("scopes", [])} or self.default_scopes
            return count, scopes
        return self.default_witness_count, self.default_scopes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policyId": self.policy_id,
            "name": self.name,
            "defaultWitnessCount": self.default_witness_count,
            "defaultScopes": [s.value for s in self.default_scopes],
            "intentOverrides": self.intent_overrides,
            "maxAttestationAgeSeconds": self.max_attestation_age_seconds,
        }


# ===========================================================================
# Witness Gateway
# ===========================================================================


class WitnessGateway:
    """
    Witness gateway implementation.

    Witness gateways provide independent verification of executions
    WITHOUT the ability to create new executions or decrypt payloads.

    CRITICAL CONSTRAINTS:
    1. NEVER creates executions
    2. NEVER decrypts payloads
    3. Only performs deterministic verification
    4. Signs attestations with its own key
    """

    def __init__(
        self,
        identity: WitnessIdentity,
        private_key: Ed25519PrivateKey,
        gateway_public_keys: Dict[str, bytes],
    ):
        """
        Initialize a witness gateway.

        Args:
            identity: This witness's identity
            private_key: Ed25519 private key for signing attestations
            gateway_public_keys: Public keys of gateways to verify (key_id -> bytes)
        """
        self._identity = identity
        self._private_key = private_key
        self._gateway_keys: Dict[str, Ed25519PublicKey] = {}

        for key_id, key_bytes in gateway_public_keys.items():
            self._gateway_keys[key_id] = Ed25519PublicKey.from_public_bytes(key_bytes)

    @property
    def identity(self) -> WitnessIdentity:
        return self._identity

    def add_gateway_key(self, key_id: str, public_key_bytes: bytes) -> None:
        """Add a gateway public key for verification."""
        self._gateway_keys[key_id] = Ed25519PublicKey.from_public_bytes(public_key_bytes)

    def verify_execution(
        self,
        envelope: CanonicalExecutionEnvelope,
        scopes: Optional[Set[WitnessScope]] = None,
    ) -> WitnessAttestation:
        """
        Verify an execution and create an attestation.

        CRITICAL: This method NEVER decrypts payloads.
        Verification is deterministic and based only on hashes and signatures.

        Args:
            envelope: The execution envelope to verify
            scopes: Verification scopes to check (defaults to supported scopes)

        Returns:
            WitnessAttestation for the execution
        """
        import uuid

        scopes_to_verify = scopes or self._identity.supported_scopes
        scope_results: Dict[str, bool] = {}

        # Verify canonical hash
        if WitnessScope.CANONICAL_HASH in scopes_to_verify:
            hash_valid = envelope.verify_hash()
            scope_results[WitnessScope.CANONICAL_HASH.value] = hash_valid

        # Verify gateway signature
        if WitnessScope.GATEWAY_SIGNATURE in scopes_to_verify:
            sig_valid = self._verify_gateway_signature(envelope)
            scope_results[WitnessScope.GATEWAY_SIGNATURE.value] = sig_valid

        # Verify lineage (if parent hash exists)
        if WitnessScope.LINEAGE in scopes_to_verify:
            # Lineage verification requires parent execution
            # For now, we just check that parent_execution_hash has correct format
            if envelope.parent_execution_hash:
                lineage_valid = len(envelope.parent_execution_hash) == 64
            else:
                lineage_valid = True  # No parent is valid
            scope_results[WitnessScope.LINEAGE.value] = lineage_valid

        # Batch membership verification
        if WitnessScope.BATCH_MEMBERSHIP in scopes_to_verify:
            if envelope.batch_membership:
                # Verify batch membership proof
                batch_valid = self._verify_batch_membership(envelope)
            else:
                batch_valid = True  # No batch is valid (not yet batched)
            scope_results[WitnessScope.BATCH_MEMBERSHIP.value] = batch_valid

        # Determine overall status
        all_passed = all(scope_results.values())
        any_passed = any(scope_results.values())

        if all_passed:
            status = AttestationStatus.VALID
        elif any_passed:
            status = AttestationStatus.PARTIAL
        else:
            status = AttestationStatus.INVALID

        # Create attestation
        attestation_id = str(uuid.uuid4())
        attestation = WitnessAttestation(
            attestation_id=attestation_id,
            witness_id=self._identity.witness_id,
            execution_id=envelope.execution_id,
            canonical_hash=envelope.canonical_hash,
            scopes_verified=list(scopes_to_verify),
            scope_results=scope_results,
            status=status,
            signature="",  # Will be set after signing
            key_id=self._identity.key_id,
        )

        # Sign the attestation
        attestation_hash = attestation.compute_attestation_hash()
        signature = self._private_key.sign(attestation_hash.encode("utf-8"))
        attestation.signature = base64.b64encode(signature).decode("ascii")

        return attestation

    def _verify_gateway_signature(self, envelope: CanonicalExecutionEnvelope) -> bool:
        """Verify the gateway signature on an envelope."""
        if envelope.gateway_signature is None:
            return False

        key_id = envelope.gateway_signature.key_id
        if key_id not in self._gateway_keys:
            return False

        try:
            public_key = self._gateway_keys[key_id]
            signature = base64.b64decode(envelope.gateway_signature.signature)
            data = envelope.canonical_hash.encode("utf-8")
            public_key.verify(signature, data)
            return True
        except InvalidSignature:
            return False
        except Exception:
            return False

    def _verify_batch_membership(self, envelope: CanonicalExecutionEnvelope) -> bool:
        """Verify batch membership proof."""
        if envelope.batch_membership is None:
            return True

        # Batch membership verification is delegated to the Merkle module
        # For now, we check that required fields exist
        required_fields = ["batchId", "leafIndex", "proof", "batchRoot"]
        return all(f in envelope.batch_membership for f in required_fields)

    def verify_attestation(self, attestation: WitnessAttestation) -> bool:
        """
        Verify another witness's attestation.

        Args:
            attestation: The attestation to verify

        Returns:
            True if the attestation signature is valid
        """
        # Get witness public key (would be from a registry in production)
        # For now, we can only verify our own attestations
        if attestation.witness_id != self._identity.witness_id:
            return False

        try:
            attestation_hash = attestation.compute_attestation_hash()
            signature = base64.b64decode(attestation.signature)
            public_key = self._private_key.public_key()
            public_key.verify(signature, attestation_hash.encode("utf-8"))
            return True
        except InvalidSignature:
            return False
        except Exception:
            return False

    @classmethod
    def create(
        cls,
        witness_id: str,
        role: WitnessRole = WitnessRole.FULL_WITNESS,
        domain: Optional[str] = None,
    ) -> tuple["WitnessGateway", WitnessIdentity]:
        """
        Create a new witness gateway with generated keys.

        For testing/development only. Production should use HSM-backed keys.

        Returns:
            Tuple of (WitnessGateway, WitnessIdentity)
        """
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        public_key_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        key_id = hashlib.sha256(public_key_bytes).hexdigest()[:16]

        # Determine supported scopes based on role
        if role == WitnessRole.FULL_WITNESS:
            scopes = {
                WitnessScope.CANONICAL_HASH,
                WitnessScope.GATEWAY_SIGNATURE,
                WitnessScope.LINEAGE,
                WitnessScope.BATCH_MEMBERSHIP,
            }
        elif role == WitnessRole.HASH_WITNESS:
            scopes = {WitnessScope.CANONICAL_HASH}
        else:  # SIGNATURE_WITNESS
            scopes = {WitnessScope.GATEWAY_SIGNATURE}

        identity = WitnessIdentity(
            witness_id=witness_id,
            key_id=key_id,
            public_key_bytes=public_key_bytes,
            role=role,
            supported_scopes=scopes,
            domain=domain,
        )

        gateway = cls(identity, private_key, {})
        return gateway, identity
