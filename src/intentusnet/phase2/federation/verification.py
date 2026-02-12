"""
Cross-Gateway Verification (Phase II)

Provides verification of executions from federated gateways.

Key concepts:
- Cross-gateway execution verification
- Multi-signature execution attestations
- Foreign execution storage (non-authoritative)
- Cross-domain replay with lineage preservation
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

from intentusnet.phase2.gateway.enforcement import (
    CanonicalExecutionEnvelope,
    GatewayIdentity,
    GatewayVerifier,
)
from intentusnet.phase2.federation.identity import (
    FederatedGatewayIdentity,
    GatewayDiscoveryService,
    TrustLevel,
)


# ===========================================================================
# Verification Results
# ===========================================================================


class VerificationScope(Enum):
    """Scope of verification performed."""
    SIGNATURE_ONLY = "signature_only"  # Only signature verified
    HASH_AND_SIGNATURE = "hash_and_signature"  # Hash and signature verified
    FULL = "full"  # Full verification including lineage


class VerificationStatus(Enum):
    """Status of verification."""
    VERIFIED = "verified"
    FAILED = "failed"
    PARTIAL = "partial"  # Some checks passed, some failed
    PENDING = "pending"  # Not yet verified
    UNTRUSTED = "untrusted"  # Gateway not trusted


@dataclass
class FederatedVerificationResult:
    """
    Result of cross-gateway verification.

    Attributes:
        execution_id: ID of the execution verified
        source_gateway_id: Gateway that created the execution
        status: Overall verification status
        scope: Scope of verification performed
        signature_valid: Whether signature is valid
        hash_valid: Whether canonical hash matches
        gateway_trusted: Whether source gateway is trusted
        lineage_verified: Whether parent lineage was verified
        error: Error message if verification failed
        verified_at: When verification was performed
    """
    execution_id: str
    source_gateway_id: str
    status: VerificationStatus
    scope: VerificationScope
    signature_valid: bool = False
    hash_valid: bool = False
    gateway_trusted: bool = False
    lineage_verified: bool = False
    error: Optional[str] = None
    verified_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "executionId": self.execution_id,
            "sourceGatewayId": self.source_gateway_id,
            "status": self.status.value,
            "scope": self.scope.value,
            "signatureValid": self.signature_valid,
            "hashValid": self.hash_valid,
            "gatewayTrusted": self.gateway_trusted,
            "lineageVerified": self.lineage_verified,
            "error": self.error,
            "verifiedAt": self.verified_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FederatedVerificationResult":
        return cls(
            execution_id=data["executionId"],
            source_gateway_id=data["sourceGatewayId"],
            status=VerificationStatus(data["status"]),
            scope=VerificationScope(data["scope"]),
            signature_valid=data.get("signatureValid", False),
            hash_valid=data.get("hashValid", False),
            gateway_trusted=data.get("gatewayTrusted", False),
            lineage_verified=data.get("lineageVerified", False),
            error=data.get("error"),
            verified_at=data.get("verifiedAt", datetime.now(timezone.utc).isoformat()),
        )


# ===========================================================================
# Multi-Signature Attestation
# ===========================================================================


@dataclass
class SignatureAttestation:
    """A single signature attestation from a gateway."""
    gateway_id: str
    key_id: str
    signature: str  # Base64-encoded
    signed_hash: str  # Hash that was signed
    signed_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gatewayId": self.gateway_id,
            "keyId": self.key_id,
            "signature": self.signature,
            "signedHash": self.signed_hash,
            "signedAt": self.signed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SignatureAttestation":
        return cls(
            gateway_id=data["gatewayId"],
            key_id=data["keyId"],
            signature=data["signature"],
            signed_hash=data["signedHash"],
            signed_at=data["signedAt"],
        )


@dataclass
class MultiSignatureAttestation:
    """
    Multi-signature attestation for an execution.

    This allows multiple gateways to attest to the same execution,
    providing stronger verification guarantees.

    Attributes:
        execution_id: ID of the attested execution
        canonical_hash: Canonical hash being attested
        attestations: List of individual signature attestations
        required_signatures: Minimum signatures required
        created_at: When the multi-sig was created
    """
    execution_id: str
    canonical_hash: str
    attestations: List[SignatureAttestation] = field(default_factory=list)
    required_signatures: int = 1
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "executionId": self.execution_id,
            "canonicalHash": self.canonical_hash,
            "attestations": [a.to_dict() for a in self.attestations],
            "requiredSignatures": self.required_signatures,
            "createdAt": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MultiSignatureAttestation":
        attestations = [
            SignatureAttestation.from_dict(a)
            for a in data.get("attestations", [])
        ]
        return cls(
            execution_id=data["executionId"],
            canonical_hash=data["canonicalHash"],
            attestations=attestations,
            required_signatures=data.get("requiredSignatures", 1),
            created_at=data.get("createdAt", datetime.now(timezone.utc).isoformat()),
        )

    def add_attestation(self, attestation: SignatureAttestation) -> None:
        """Add an attestation to the multi-sig."""
        # Verify the attestation is for the same hash
        if attestation.signed_hash != self.canonical_hash:
            raise ValueError(
                f"Attestation hash mismatch: expected {self.canonical_hash}, "
                f"got {attestation.signed_hash}"
            )

        # Check for duplicate gateway
        for existing in self.attestations:
            if existing.gateway_id == attestation.gateway_id:
                raise ValueError(
                    f"Gateway {attestation.gateway_id} has already attested"
                )

        self.attestations.append(attestation)

    def has_quorum(self) -> bool:
        """Check if the required number of signatures has been reached."""
        return len(self.attestations) >= self.required_signatures

    def get_attesting_gateways(self) -> List[str]:
        """Get list of gateway IDs that have attested."""
        return [a.gateway_id for a in self.attestations]


# ===========================================================================
# Foreign Execution Record
# ===========================================================================


@dataclass
class ForeignExecutionRecord:
    """
    A non-authoritative record of an execution from another gateway.

    Foreign executions are stored for:
    - Cross-domain replay with lineage preservation
    - Audit trail continuity
    - Historical reference

    IMPORTANT: These records are NOT authoritative.
    The source gateway is the authority for the execution.

    Attributes:
        envelope: The canonical execution envelope
        source_gateway: Identity of the source gateway
        received_at: When this record was received
        verification_result: Result of verification
        multi_sig: Optional multi-signature attestation
        local_reference_id: Local reference ID (different from execution_id)
    """
    envelope: CanonicalExecutionEnvelope
    source_gateway: FederatedGatewayIdentity
    received_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    verification_result: Optional[FederatedVerificationResult] = None
    multi_sig: Optional[MultiSignatureAttestation] = None
    local_reference_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "envelope": self.envelope.to_dict(),
            "sourceGateway": self.source_gateway.to_dict(),
            "receivedAt": self.received_at,
            "verificationResult": (
                self.verification_result.to_dict()
                if self.verification_result else None
            ),
            "multiSig": self.multi_sig.to_dict() if self.multi_sig else None,
            "localReferenceId": self.local_reference_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ForeignExecutionRecord":
        vr_data = data.get("verificationResult")
        ms_data = data.get("multiSig")

        return cls(
            envelope=CanonicalExecutionEnvelope.from_dict(data["envelope"]),
            source_gateway=FederatedGatewayIdentity.from_dict(data["sourceGateway"]),
            received_at=data.get("receivedAt", datetime.now(timezone.utc).isoformat()),
            verification_result=(
                FederatedVerificationResult.from_dict(vr_data)
                if vr_data else None
            ),
            multi_sig=(
                MultiSignatureAttestation.from_dict(ms_data)
                if ms_data else None
            ),
            local_reference_id=data.get("localReferenceId"),
        )

    def is_verified(self) -> bool:
        """Check if the execution has been verified."""
        return (
            self.verification_result is not None
            and self.verification_result.status == VerificationStatus.VERIFIED
        )

    def is_trusted(self) -> bool:
        """Check if the source gateway is trusted."""
        return self.source_gateway.is_trusted()


# ===========================================================================
# Cross-Gateway Verifier
# ===========================================================================


class CrossGatewayVerifier:
    """
    Verifier for cross-gateway executions.

    Provides verification of executions from federated gateways,
    including signature verification, hash validation, and trust checks.
    """

    def __init__(
        self,
        discovery_service: GatewayDiscoveryService,
        local_verifier: Optional[GatewayVerifier] = None,
    ):
        self._discovery = discovery_service
        self._local_verifier = local_verifier or GatewayVerifier()
        self._foreign_records: Dict[str, ForeignExecutionRecord] = {}

    def verify_execution(
        self,
        envelope: CanonicalExecutionEnvelope,
        scope: VerificationScope = VerificationScope.FULL,
    ) -> FederatedVerificationResult:
        """
        Verify an execution from a federated gateway.

        Args:
            envelope: The canonical execution envelope to verify
            scope: Scope of verification to perform

        Returns:
            FederatedVerificationResult with verification status
        """
        # Get source gateway identity
        federated_identity = self._discovery.get_gateway(envelope.gateway_id)

        if federated_identity is None:
            return FederatedVerificationResult(
                execution_id=envelope.execution_id,
                source_gateway_id=envelope.gateway_id,
                status=VerificationStatus.UNTRUSTED,
                scope=scope,
                error=f"Gateway {envelope.gateway_id} not found in discovery cache",
            )

        # Check gateway trust
        gateway_trusted = federated_identity.is_trusted()

        # Verify canonical hash
        hash_valid = envelope.verify_hash()

        # Verify signature
        signature_valid = self._verify_signature(envelope, federated_identity)

        # Determine overall status
        if signature_valid and hash_valid:
            if gateway_trusted:
                status = VerificationStatus.VERIFIED
            else:
                status = VerificationStatus.PARTIAL
        elif signature_valid or hash_valid:
            status = VerificationStatus.PARTIAL
            self._discovery.record_verification_failure(envelope.gateway_id)
        else:
            status = VerificationStatus.FAILED
            self._discovery.record_verification_failure(envelope.gateway_id)

        # Verify lineage if full scope requested
        lineage_verified = False
        if scope == VerificationScope.FULL and envelope.parent_execution_hash:
            lineage_verified = self._verify_lineage(envelope)

        return FederatedVerificationResult(
            execution_id=envelope.execution_id,
            source_gateway_id=envelope.gateway_id,
            status=status,
            scope=scope,
            signature_valid=signature_valid,
            hash_valid=hash_valid,
            gateway_trusted=gateway_trusted,
            lineage_verified=lineage_verified,
        )

    def _verify_signature(
        self,
        envelope: CanonicalExecutionEnvelope,
        federated_identity: FederatedGatewayIdentity,
    ) -> bool:
        """Verify the gateway signature on an envelope."""
        if envelope.gateway_signature is None:
            return False

        try:
            # Get public key from identity
            public_key = Ed25519PublicKey.from_public_bytes(
                federated_identity.identity.public_key_bytes
            )

            # Decode signature
            signature = base64.b64decode(envelope.gateway_signature.signature)

            # Verify
            data = envelope.canonical_hash.encode("utf-8")
            public_key.verify(signature, data)
            return True

        except InvalidSignature:
            return False
        except Exception:
            return False

    def _verify_lineage(self, envelope: CanonicalExecutionEnvelope) -> bool:
        """Verify the parent execution lineage."""
        if envelope.parent_execution_hash is None:
            return True  # No parent to verify

        # Check if we have the parent execution
        for record in self._foreign_records.values():
            if record.envelope.canonical_hash == envelope.parent_execution_hash:
                # Found parent, verify it's verified
                return record.is_verified()

        # Parent not found locally - can't verify lineage
        return False

    def store_foreign_execution(
        self,
        envelope: CanonicalExecutionEnvelope,
        verify: bool = True,
    ) -> ForeignExecutionRecord:
        """
        Store a foreign execution record.

        Args:
            envelope: The canonical execution envelope
            verify: Whether to verify the execution

        Returns:
            ForeignExecutionRecord for the stored execution
        """
        # Get source gateway
        federated_identity = self._discovery.get_gateway(envelope.gateway_id)

        if federated_identity is None:
            # Create minimal identity for untrusted gateway with NO valid key
            # Empty key explicitly prevents signature verification
            federated_identity = FederatedGatewayIdentity(
                gateway_id=envelope.gateway_id,
                domain="unknown",
                identity=GatewayIdentity(
                    gateway_id=envelope.gateway_id,
                    key_id="invalid-unknown-gateway",
                    public_key_bytes=b"",  # Empty = explicitly invalid, cannot verify
                ),
                trust_level=TrustLevel.UNTRUSTED,
            )

        # Verify if requested
        verification_result = None
        if verify:
            verification_result = self.verify_execution(envelope)

        # Create record
        record = ForeignExecutionRecord(
            envelope=envelope,
            source_gateway=federated_identity,
            verification_result=verification_result,
        )

        self._foreign_records[envelope.execution_id] = record
        return record

    def get_foreign_execution(
        self,
        execution_id: str,
    ) -> Optional[ForeignExecutionRecord]:
        """Get a stored foreign execution record."""
        return self._foreign_records.get(execution_id)

    def verify_multi_signature(
        self,
        multi_sig: MultiSignatureAttestation,
    ) -> Dict[str, bool]:
        """
        Verify all signatures in a multi-signature attestation.

        Returns:
            Dict mapping gateway_id to verification result
        """
        results: Dict[str, bool] = {}

        for attestation in multi_sig.attestations:
            federated_identity = self._discovery.get_gateway(attestation.gateway_id)

            if federated_identity is None:
                results[attestation.gateway_id] = False
                continue

            try:
                public_key = Ed25519PublicKey.from_public_bytes(
                    federated_identity.identity.public_key_bytes
                )
                signature = base64.b64decode(attestation.signature)
                data = attestation.signed_hash.encode("utf-8")
                public_key.verify(signature, data)
                results[attestation.gateway_id] = True
            except Exception:
                results[attestation.gateway_id] = False

        return results

    def create_attestation(
        self,
        execution: CanonicalExecutionEnvelope,
        signer_gateway_id: str,
        signer_key_id: str,
        sign_func,  # Callable[[bytes], bytes]
    ) -> SignatureAttestation:
        """
        Create a signature attestation for an execution.

        Args:
            execution: The execution to attest
            signer_gateway_id: Gateway ID of the signer
            signer_key_id: Key ID used for signing
            sign_func: Function to sign data

        Returns:
            SignatureAttestation for the execution
        """
        data = execution.canonical_hash.encode("utf-8")
        signature = sign_func(data)

        return SignatureAttestation(
            gateway_id=signer_gateway_id,
            key_id=signer_key_id,
            signature=base64.b64encode(signature).decode("ascii"),
            signed_hash=execution.canonical_hash,
            signed_at=datetime.now(timezone.utc).isoformat(),
        )
