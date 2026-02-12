"""
Time Machine API Core (Phase II)

Provides the backend API for the Time Machine UI.

CRITICAL CONSTRAINTS:
- Read-only by default
- No silent failures
- No protocol shortcuts
- UI consumes backend contracts exactly
- UI must not invent data
- Signature MUST verify before rendering content
- Decryption must be explicit and user-triggered
- Never auto-decrypt
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from intentusnet.phase2.gateway.enforcement import (
    CanonicalExecutionEnvelope,
    GatewayVerifier,
)
from intentusnet.phase2.gateway.encryption import (
    EncryptedExecutionPayload,
    SectionType,
    DecryptionRequest,
    DecryptionResult,
    SectionEncryptor,
    ExecutionDEK,
)
from intentusnet.phase2.merkle.batch import (
    ExecutionBatch,
    BatchVerifier,
)
from intentusnet.phase2.witness.attestation import (
    WitnessAttestation,
)
from intentusnet.phase2.regulator.compliance import (
    ComplianceStatus,
)


# ===========================================================================
# Enums and Types
# ===========================================================================


class VerificationStatus(Enum):
    """Verification status for executions."""
    VERIFIED = "verified"  # Signature verified
    UNVERIFIED = "unverified"  # Not yet verified
    FAILED = "failed"  # Verification failed
    PARTIAL = "partial"  # Some checks passed


class SortOrder(Enum):
    """Sort order for timeline queries."""
    ASC = "asc"
    DESC = "desc"


# ===========================================================================
# Query Types
# ===========================================================================


@dataclass
class PaginationParams:
    """Pagination parameters for queries."""
    offset: int = 0
    limit: int = 50
    sort_order: SortOrder = SortOrder.DESC

    def to_dict(self) -> Dict[str, Any]:
        return {
            "offset": self.offset,
            "limit": self.limit,
            "sortOrder": self.sort_order.value,
        }


@dataclass
class TimelineFilter:
    """
    Filter parameters for timeline queries.

    Attributes:
        intent_names: Filter by intent names
        model_ids: Filter by model IDs (from metadata)
        trust_domains: Filter by trust domains
        status: Filter by verification status
        gateway_ids: Filter by source gateway
        start_time: Start of time range (ISO 8601)
        end_time: End of time range (ISO 8601)
        has_parent: Filter by whether execution has parent
        batch_ids: Filter by batch membership
    """
    intent_names: Optional[Set[str]] = None
    model_ids: Optional[Set[str]] = None
    trust_domains: Optional[Set[str]] = None
    status: Optional[Set[VerificationStatus]] = None
    gateway_ids: Optional[Set[str]] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    has_parent: Optional[bool] = None
    batch_ids: Optional[Set[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intentNames": list(self.intent_names) if self.intent_names else None,
            "modelIds": list(self.model_ids) if self.model_ids else None,
            "trustDomains": list(self.trust_domains) if self.trust_domains else None,
            "status": [s.value for s in self.status] if self.status else None,
            "gatewayIds": list(self.gateway_ids) if self.gateway_ids else None,
            "startTime": self.start_time,
            "endTime": self.end_time,
            "hasParent": self.has_parent,
            "batchIds": list(self.batch_ids) if self.batch_ids else None,
        }


@dataclass
class ExecutionQuery:
    """Query for execution retrieval."""
    execution_id: str
    include_encrypted_sections: bool = True
    verify_signature: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "executionId": self.execution_id,
            "includeEncryptedSections": self.include_encrypted_sections,
            "verifySignature": self.verify_signature,
        }


# ===========================================================================
# Response Types
# ===========================================================================


@dataclass
class TimelineEntry:
    """
    A single entry in the timeline view.

    Attributes:
        execution_id: Unique execution identifier (always visible)
        intent_name: Name of the intent
        intent_version: Version of the intent
        created_at: When the execution was created
        gateway_id: Gateway that created the execution
        verification_status: Current verification status
        has_parent: Whether execution has a parent
        parent_execution_id: Parent execution ID (if any)
        has_children: Whether execution has children
        batch_id: Batch ID (if batched)
        input_encrypted: Whether input is encrypted
        output_encrypted: Whether output is encrypted
        trace_encrypted: Whether trace is encrypted
    """
    execution_id: str
    intent_name: str
    intent_version: str
    created_at: str
    gateway_id: str
    verification_status: VerificationStatus
    has_parent: bool = False
    parent_execution_id: Optional[str] = None
    has_children: bool = False
    batch_id: Optional[str] = None
    input_encrypted: bool = False
    output_encrypted: bool = False
    trace_encrypted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "executionId": self.execution_id,
            "intentName": self.intent_name,
            "intentVersion": self.intent_version,
            "createdAt": self.created_at,
            "gatewayId": self.gateway_id,
            "verificationStatus": self.verification_status.value,
            "hasParent": self.has_parent,
            "parentExecutionId": self.parent_execution_id,
            "hasChildren": self.has_children,
            "batchId": self.batch_id,
            "inputEncrypted": self.input_encrypted,
            "outputEncrypted": self.output_encrypted,
            "traceEncrypted": self.trace_encrypted,
        }


@dataclass
class SectionContent:
    """
    Content of a section, with encryption state.

    Attributes:
        section_type: Type of section
        is_encrypted: Whether section is currently encrypted
        content: Section content (None if encrypted and not decrypted)
        decryption_error: Error message if decryption failed
    """
    section_type: SectionType
    is_encrypted: bool
    content: Optional[Dict[str, Any]] = None
    decryption_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sectionType": self.section_type.value,
            "isEncrypted": self.is_encrypted,
            "content": self.content,
            "decryptionError": self.decryption_error,
        }


@dataclass
class ExecutionDetailResponse:
    """
    Detailed execution response for the detail view.

    CRITICAL: verification_status MUST be checked before trusting any content.

    Attributes:
        execution_id: Unique execution identifier
        canonical_hash: Hash of the execution
        gateway_id: Gateway that created the execution
        created_at: When the execution was created

        intent_name: Name of the intent
        intent_version: Version of the intent

        verification_status: MUST BE CHECKED FIRST
        signature_verified: Whether gateway signature verified
        hash_verified: Whether canonical hash verified

        input_section: Input section with encryption state
        output_section: Output section with encryption state
        trace_section: Trace section with encryption state
        metadata: Metadata (not encrypted by default)

        parent_execution_hash: Parent execution hash (if any)
        witness_attestations: List of witness attestations
        batch_membership: Batch membership info
        compliance_status: Compliance status (if available)
    """
    execution_id: str
    canonical_hash: str
    gateway_id: str
    created_at: str

    intent_name: str
    intent_version: str

    verification_status: VerificationStatus
    signature_verified: bool
    hash_verified: bool

    input_section: SectionContent
    output_section: SectionContent
    trace_section: SectionContent
    metadata: Dict[str, Any]

    parent_execution_hash: Optional[str] = None
    witness_attestations: List[WitnessAttestation] = field(default_factory=list)
    batch_membership: Optional[Dict[str, Any]] = None
    compliance_status: Optional[ComplianceStatus] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "executionId": self.execution_id,
            "canonicalHash": self.canonical_hash,
            "gatewayId": self.gateway_id,
            "createdAt": self.created_at,
            "intentName": self.intent_name,
            "intentVersion": self.intent_version,
            "verificationStatus": self.verification_status.value,
            "signatureVerified": self.signature_verified,
            "hashVerified": self.hash_verified,
            "inputSection": self.input_section.to_dict(),
            "outputSection": self.output_section.to_dict(),
            "traceSection": self.trace_section.to_dict(),
            "metadata": self.metadata,
            "parentExecutionHash": self.parent_execution_hash,
            "witnessAttestations": [a.to_dict() for a in self.witness_attestations],
            "batchMembership": self.batch_membership,
            "complianceStatus": (
                self.compliance_status.value if self.compliance_status else None
            ),
        }


@dataclass
class ProofExportBundle:
    """
    Exportable proof bundle for offline verification.

    Contains all proofs needed to verify an execution offline.

    Attributes:
        execution_id: Execution identifier
        canonical_hash: Canonical hash of the execution
        gateway_signature: Gateway signature data
        witness_attestations: List of witness attestations
        batch_inclusion_proof: Batch inclusion proof (if batched)
        log_inclusion_proof: Transparency log proof (if published)
        checkpoint: Transparency checkpoint
        exported_at: When the bundle was exported
        bundle_hash: Hash of the bundle for integrity
    """
    execution_id: str
    canonical_hash: str
    gateway_signature: Dict[str, Any]
    witness_attestations: List[Dict[str, Any]] = field(default_factory=list)
    batch_inclusion_proof: Optional[Dict[str, Any]] = None
    log_inclusion_proof: Optional[Dict[str, Any]] = None
    checkpoint: Optional[Dict[str, Any]] = None
    exported_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    bundle_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "executionId": self.execution_id,
            "canonicalHash": self.canonical_hash,
            "gatewaySignature": self.gateway_signature,
            "witnessAttestations": self.witness_attestations,
            "batchInclusionProof": self.batch_inclusion_proof,
            "logInclusionProof": self.log_inclusion_proof,
            "checkpoint": self.checkpoint,
            "exportedAt": self.exported_at,
            "bundleHash": self.bundle_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProofExportBundle":
        return cls(
            execution_id=data["executionId"],
            canonical_hash=data["canonicalHash"],
            gateway_signature=data["gatewaySignature"],
            witness_attestations=data.get("witnessAttestations", []),
            batch_inclusion_proof=data.get("batchInclusionProof"),
            log_inclusion_proof=data.get("logInclusionProof"),
            checkpoint=data.get("checkpoint"),
            exported_at=data.get("exportedAt", datetime.now(timezone.utc).isoformat()),
            bundle_hash=data.get("bundleHash"),
        )

    def compute_bundle_hash(self) -> str:
        """Compute hash of the bundle for integrity checking."""
        import hashlib

        content = {
            "executionId": self.execution_id,
            "canonicalHash": self.canonical_hash,
            "gatewaySignature": self.gateway_signature,
            "witnessAttestations": self.witness_attestations,
            "batchInclusionProof": self.batch_inclusion_proof,
            "logInclusionProof": self.log_inclusion_proof,
            "checkpoint": self.checkpoint,
        }
        canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ===========================================================================
# Time Machine API
# ===========================================================================


class TimeMachineAPI:
    """
    Time Machine Backend API.

    Provides read-only, verification-first access to execution history.

    CRITICAL CONSTRAINTS:
    1. Signature MUST verify before rendering content
    2. Decryption is ALWAYS explicit and user-triggered
    3. Never auto-decrypt
    4. No silent failures - all errors are surfaced
    """

    def __init__(
        self,
        gateway_verifier: GatewayVerifier,
        section_encryptor: Optional[SectionEncryptor] = None,
        batch_verifier: Optional[BatchVerifier] = None,
    ):
        """
        Initialize the Time Machine API.

        Args:
            gateway_verifier: Verifier for gateway signatures
            section_encryptor: Encryptor for section decryption
            batch_verifier: Verifier for batch proofs
        """
        self._verifier = gateway_verifier
        self._encryptor = section_encryptor or SectionEncryptor()
        self._batch_verifier = batch_verifier

        # Storage (in production, this would be a database)
        self._executions: Dict[str, CanonicalExecutionEnvelope] = {}
        self._encrypted_payloads: Dict[str, EncryptedExecutionPayload] = {}
        self._batches: Dict[str, ExecutionBatch] = {}
        self._witness_attestations: Dict[str, List[WitnessAttestation]] = {}
        self._deks: Dict[str, ExecutionDEK] = {}  # For testing only

    # -----------------------------------------------------------------------
    # Storage (for testing/demo)
    # -----------------------------------------------------------------------

    def store_execution(
        self,
        envelope: CanonicalExecutionEnvelope,
        encrypted_payload: Optional[EncryptedExecutionPayload] = None,
        dek: Optional[ExecutionDEK] = None,
    ) -> None:
        """Store an execution for retrieval."""
        self._executions[envelope.execution_id] = envelope
        if encrypted_payload:
            self._encrypted_payloads[envelope.execution_id] = encrypted_payload
        if dek:
            self._deks[envelope.execution_id] = dek

    def store_batch(self, batch: ExecutionBatch) -> None:
        """Store a batch for retrieval."""
        self._batches[batch.batch_id] = batch

    def store_witness_attestation(
        self,
        execution_id: str,
        attestation: WitnessAttestation,
    ) -> None:
        """Store a witness attestation."""
        if execution_id not in self._witness_attestations:
            self._witness_attestations[execution_id] = []
        self._witness_attestations[execution_id].append(attestation)

    # -----------------------------------------------------------------------
    # Timeline Queries
    # -----------------------------------------------------------------------

    def query_timeline(
        self,
        filter_params: Optional[TimelineFilter] = None,
        pagination: Optional[PaginationParams] = None,
    ) -> Tuple[List[TimelineEntry], int]:
        """
        Query the execution timeline.

        Args:
            filter_params: Optional filter parameters
            pagination: Optional pagination parameters

        Returns:
            Tuple of (entries, total_count)
        """
        pagination = pagination or PaginationParams()
        filter_params = filter_params or TimelineFilter()

        # Get all executions and filter
        filtered: List[CanonicalExecutionEnvelope] = []

        for envelope in self._executions.values():
            if self._matches_filter(envelope, filter_params):
                filtered.append(envelope)

        # Sort by creation time
        reverse = pagination.sort_order == SortOrder.DESC
        filtered.sort(key=lambda e: e.created_at, reverse=reverse)

        total_count = len(filtered)

        # Apply pagination
        start = pagination.offset
        end = start + pagination.limit
        page = filtered[start:end]

        # Convert to timeline entries
        entries: List[TimelineEntry] = []
        for envelope in page:
            # Verify signature for status
            verified = self._verifier.verify_envelope(envelope)
            status = VerificationStatus.VERIFIED if verified else VerificationStatus.UNVERIFIED

            # Find batch
            batch_id = None
            for batch in self._batches.values():
                if batch.contains_execution(envelope.execution_id):
                    batch_id = batch.batch_id
                    break

            entry = TimelineEntry(
                execution_id=envelope.execution_id,
                intent_name=envelope.intent_name,
                intent_version=envelope.intent_version,
                created_at=envelope.created_at,
                gateway_id=envelope.gateway_id,
                verification_status=status,
                has_parent=envelope.parent_execution_hash is not None,
                parent_execution_id=self._find_parent_id(envelope.parent_execution_hash),
                batch_id=batch_id,
                input_encrypted=envelope.input_encrypted,
                output_encrypted=envelope.output_encrypted,
                trace_encrypted=envelope.trace_encrypted,
            )
            entries.append(entry)

        return entries, total_count

    def _matches_filter(
        self,
        envelope: CanonicalExecutionEnvelope,
        filter_params: TimelineFilter,
    ) -> bool:
        """Check if an envelope matches the filter."""
        if filter_params.intent_names and envelope.intent_name not in filter_params.intent_names:
            return False

        if filter_params.gateway_ids and envelope.gateway_id not in filter_params.gateway_ids:
            return False

        if filter_params.has_parent is not None:
            has_parent = envelope.parent_execution_hash is not None
            if has_parent != filter_params.has_parent:
                return False

        if filter_params.start_time:
            if envelope.created_at < filter_params.start_time:
                return False

        if filter_params.end_time:
            if envelope.created_at > filter_params.end_time:
                return False

        return True

    def _find_parent_id(self, parent_hash: Optional[str]) -> Optional[str]:
        """Find parent execution ID by hash."""
        if parent_hash is None:
            return None

        for envelope in self._executions.values():
            if envelope.canonical_hash == parent_hash:
                return envelope.execution_id
        return None

    # -----------------------------------------------------------------------
    # Execution Detail
    # -----------------------------------------------------------------------

    def get_execution_detail(
        self,
        query: ExecutionQuery,
    ) -> Optional[ExecutionDetailResponse]:
        """
        Get detailed execution information.

        CRITICAL: Check verification_status before trusting content.

        Args:
            query: Execution query parameters

        Returns:
            ExecutionDetailResponse or None if not found
        """
        envelope = self._executions.get(query.execution_id)
        if envelope is None:
            return None

        # CRITICAL: Verify signature FIRST
        signature_verified = False
        hash_verified = False

        if query.verify_signature:
            signature_verified = self._verifier.verify_envelope(envelope)
            hash_verified = envelope.verify_hash()

        if signature_verified and hash_verified:
            verification_status = VerificationStatus.VERIFIED
        elif signature_verified or hash_verified:
            verification_status = VerificationStatus.PARTIAL
        else:
            verification_status = VerificationStatus.UNVERIFIED

        # Build section content
        input_section = SectionContent(
            section_type=SectionType.INPUT,
            is_encrypted=envelope.input_encrypted,
            content=envelope.input if not envelope.input_encrypted else None,
        )

        output_section = SectionContent(
            section_type=SectionType.OUTPUT,
            is_encrypted=envelope.output_encrypted,
            content=envelope.output if not envelope.output_encrypted else None,
        )

        trace_section = SectionContent(
            section_type=SectionType.TRACE,
            is_encrypted=envelope.trace_encrypted,
            content={"trace": envelope.trace} if envelope.trace and not envelope.trace_encrypted else None,
        )

        # Get witness attestations
        attestations = self._witness_attestations.get(query.execution_id, [])

        # Find batch membership
        batch_membership = None
        for batch in self._batches.values():
            if batch.contains_execution(query.execution_id):
                proof = batch.get_inclusion_proof(query.execution_id)
                if proof:
                    batch_membership = {
                        "batchId": batch.batch_id,
                        "leafIndex": proof.leaf.leaf_index,
                        "batchRootHash": proof.batch_root_hash,
                    }
                break

        return ExecutionDetailResponse(
            execution_id=envelope.execution_id,
            canonical_hash=envelope.canonical_hash,
            gateway_id=envelope.gateway_id,
            created_at=envelope.created_at,
            intent_name=envelope.intent_name,
            intent_version=envelope.intent_version,
            verification_status=verification_status,
            signature_verified=signature_verified,
            hash_verified=hash_verified,
            input_section=input_section,
            output_section=output_section,
            trace_section=trace_section,
            metadata=envelope.metadata,
            parent_execution_hash=envelope.parent_execution_hash,
            witness_attestations=attestations,
            batch_membership=batch_membership,
        )

    # -----------------------------------------------------------------------
    # Explicit Decryption
    # -----------------------------------------------------------------------

    def request_decryption(
        self,
        execution_id: str,
        section_type: SectionType,
        dek: Optional[ExecutionDEK] = None,
    ) -> DecryptionResult:
        """
        Request decryption of a section.

        CRITICAL: This is EXPLICIT decryption - never auto-decrypt.

        Args:
            execution_id: Execution to decrypt
            section_type: Section to decrypt
            dek: Data encryption key (required for decryption)

        Returns:
            DecryptionResult with plaintext or error
        """
        envelope = self._executions.get(execution_id)
        if envelope is None:
            return DecryptionResult(
                execution_id=execution_id,
                section_type=section_type,
                plaintext=None,
                success=False,
                error="Execution not found",
            )

        # CRITICAL: Verify signature BEFORE decryption
        if not self._verifier.verify_envelope(envelope):
            return DecryptionResult(
                execution_id=execution_id,
                section_type=section_type,
                plaintext=None,
                success=False,
                error="Signature verification FAILED - decryption blocked",
            )

        # Get encrypted payload
        encrypted_payload = self._encrypted_payloads.get(execution_id)
        if encrypted_payload is None:
            return DecryptionResult(
                execution_id=execution_id,
                section_type=section_type,
                plaintext=None,
                success=False,
                error="Encrypted payload not found",
            )

        # Get DEK (from parameter or storage)
        if dek is None:
            dek = self._deks.get(execution_id)

        if dek is None:
            return DecryptionResult(
                execution_id=execution_id,
                section_type=section_type,
                plaintext=None,
                success=False,
                error="DEK not provided - decryption requires explicit key",
            )

        # Get encrypted section
        section = encrypted_payload.get_section(section_type)
        if section is None:
            return DecryptionResult(
                execution_id=execution_id,
                section_type=section_type,
                plaintext=None,
                success=False,
                error=f"Section {section_type.value} not encrypted",
            )

        # Create decryption request
        request = DecryptionRequest(
            execution_id=execution_id,
            section_type=section_type,
            signature_verified=True,  # We verified above
            dek=dek,
        )

        # Decrypt
        return self._encryptor.decrypt_section(section, request)

    # -----------------------------------------------------------------------
    # Proof Export
    # -----------------------------------------------------------------------

    def export_proof_bundle(
        self,
        execution_id: str,
    ) -> Optional[ProofExportBundle]:
        """
        Export a proof bundle for offline verification.

        Args:
            execution_id: Execution to export proofs for

        Returns:
            ProofExportBundle or None if not found
        """
        envelope = self._executions.get(execution_id)
        if envelope is None:
            return None

        # Get gateway signature
        gateway_signature: Dict[str, Any] = {}
        if envelope.gateway_signature:
            gateway_signature = envelope.gateway_signature.to_dict()

        # Get witness attestations
        attestations = self._witness_attestations.get(execution_id, [])
        attestation_dicts = [a.to_dict() for a in attestations]

        # Get batch inclusion proof
        batch_proof: Optional[Dict[str, Any]] = None
        for batch in self._batches.values():
            if batch.contains_execution(execution_id):
                proof = batch.get_inclusion_proof(execution_id)
                if proof:
                    batch_proof = proof.to_dict()
                break

        bundle = ProofExportBundle(
            execution_id=execution_id,
            canonical_hash=envelope.canonical_hash,
            gateway_signature=gateway_signature,
            witness_attestations=attestation_dicts,
            batch_inclusion_proof=batch_proof,
        )

        bundle.bundle_hash = bundle.compute_bundle_hash()
        return bundle

    # -----------------------------------------------------------------------
    # Verification
    # -----------------------------------------------------------------------

    def verify_execution(
        self,
        execution_id: str,
    ) -> Dict[str, bool]:
        """
        Verify all aspects of an execution.

        Returns:
            Dict mapping check name to result
        """
        envelope = self._executions.get(execution_id)
        if envelope is None:
            return {"found": False}

        results: Dict[str, bool] = {
            "found": True,
            "hashValid": envelope.verify_hash(),
            "signatureValid": self._verifier.verify_envelope(envelope),
        }

        # Verify batch membership
        for batch in self._batches.values():
            if batch.contains_execution(execution_id):
                proof = batch.get_inclusion_proof(execution_id)
                results["batchMembership"] = proof.verify() if proof else False
                break

        return results
