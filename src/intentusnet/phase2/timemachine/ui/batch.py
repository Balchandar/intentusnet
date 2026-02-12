"""
Batch & Transparency View (Time Machine UI - Phase II)

Provides visualization of Merkle batch membership and transparency logs.

UI REQUIREMENTS:
- Show Merkle batch membership
- Show inclusion proof
- Show transparency log inclusion
- Show regulator compliance status
- Show SLA timing compliance
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from intentusnet.phase2.merkle.batch import (
    ExecutionBatch,
    BatchInclusionProof,
)
from intentusnet.phase2.transparency.log import (
    LogInclusionProof,
    TransparencyCheckpoint,
)
from intentusnet.phase2.regulator.compliance import (
    ComplianceStatus,
    ComplianceProofPackage,
    SLAViolation,
)


# ===========================================================================
# Batch Membership Info
# ===========================================================================


@dataclass
class BatchMembershipInfo:
    """
    Batch membership information for display.

    Attributes:
        batch_id: Batch identifier
        batch_root_hash: Root hash of the batch
        leaf_index: Index of this execution in the batch
        leaf_count: Total number of executions in batch
        gateway_id: Gateway that created the batch
        created_at: When the batch was created
        sealed_at: When the batch was sealed
        has_proof: Whether inclusion proof is available
    """
    batch_id: str
    batch_root_hash: str
    leaf_index: int
    leaf_count: int
    gateway_id: str
    created_at: str
    sealed_at: Optional[str] = None
    has_proof: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batchId": self.batch_id,
            "batchRootHash": self.batch_root_hash,
            "leafIndex": self.leaf_index,
            "leafCount": self.leaf_count,
            "gatewayId": self.gateway_id,
            "createdAt": self.created_at,
            "sealedAt": self.sealed_at,
            "hasProof": self.has_proof,
        }


# ===========================================================================
# Inclusion Proof Info
# ===========================================================================


@dataclass
class InclusionProofInfo:
    """
    Inclusion proof information for display.

    Attributes:
        proof_type: Type of proof (batch or log)
        is_valid: Whether proof is valid
        leaf_hash: Hash of the leaf
        root_hash: Root hash being proved against
        proof_path_length: Number of hashes in proof path
        verified_at: When proof was verified
    """
    proof_type: str  # "batch" or "log"
    is_valid: bool
    leaf_hash: str
    root_hash: str
    proof_path_length: int
    verified_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proofType": self.proof_type,
            "isValid": self.is_valid,
            "leafHash": self.leaf_hash,
            "rootHash": self.root_hash,
            "proofPathLength": self.proof_path_length,
            "verifiedAt": self.verified_at,
        }


# ===========================================================================
# Transparency Log Info
# ===========================================================================


@dataclass
class TransparencyLogInfo:
    """
    Transparency log information for display.

    Attributes:
        log_id: Log identifier
        entry_index: Index of the batch in the log
        log_tree_size: Size of the log
        log_root_hash: Current root hash of the log
        checkpoint_timestamp: Latest checkpoint timestamp
        has_proof: Whether inclusion proof is available
    """
    log_id: str
    entry_index: int
    log_tree_size: int
    log_root_hash: str
    checkpoint_timestamp: Optional[str] = None
    has_proof: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "logId": self.log_id,
            "entryIndex": self.entry_index,
            "logTreeSize": self.log_tree_size,
            "logRootHash": self.log_root_hash,
            "checkpointTimestamp": self.checkpoint_timestamp,
            "hasProof": self.has_proof,
        }


# ===========================================================================
# Compliance Info
# ===========================================================================


@dataclass
class ComplianceInfo:
    """
    Compliance information for display.

    Attributes:
        status: Overall compliance status
        jurisdiction_id: Applicable jurisdiction
        is_compliant: Whether execution is compliant
        violations: List of SLA violations
        proof_complete: Whether compliance proof is complete
        witness_count: Number of witness attestations
        required_witnesses: Required number of witnesses
    """
    status: ComplianceStatus
    jurisdiction_id: str
    is_compliant: bool
    violations: List[SLAViolation] = field(default_factory=list)
    proof_complete: bool = False
    witness_count: int = 0
    required_witnesses: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "jurisdictionId": self.jurisdiction_id,
            "isCompliant": self.is_compliant,
            "violations": [v.to_dict() for v in self.violations],
            "proofComplete": self.proof_complete,
            "witnessCount": self.witness_count,
            "requiredWitnesses": self.required_witnesses,
        }


# ===========================================================================
# Batch View State
# ===========================================================================


@dataclass
class BatchViewState:
    """
    State for the batch & transparency view.

    Attributes:
        execution_id: Execution being viewed
        batch_membership: Batch membership info
        batch_inclusion_proof: Batch inclusion proof info
        transparency_log: Transparency log info
        log_inclusion_proof: Log inclusion proof info
        compliance: Compliance info
        checkpoint: Latest transparency checkpoint
        loading: Whether data is loading
        error: Error message if loading failed
    """
    execution_id: str
    batch_membership: Optional[BatchMembershipInfo] = None
    batch_inclusion_proof: Optional[InclusionProofInfo] = None
    transparency_log: Optional[TransparencyLogInfo] = None
    log_inclusion_proof: Optional[InclusionProofInfo] = None
    compliance: Optional[ComplianceInfo] = None
    checkpoint: Optional[Dict[str, Any]] = None
    loading: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "executionId": self.execution_id,
            "batchMembership": (
                self.batch_membership.to_dict()
                if self.batch_membership else None
            ),
            "batchInclusionProof": (
                self.batch_inclusion_proof.to_dict()
                if self.batch_inclusion_proof else None
            ),
            "transparencyLog": (
                self.transparency_log.to_dict()
                if self.transparency_log else None
            ),
            "logInclusionProof": (
                self.log_inclusion_proof.to_dict()
                if self.log_inclusion_proof else None
            ),
            "compliance": self.compliance.to_dict() if self.compliance else None,
            "checkpoint": self.checkpoint,
            "loading": self.loading,
            "error": self.error,
        }


# ===========================================================================
# Batch View
# ===========================================================================


class BatchView:
    """
    Batch & Transparency view controller for the Time Machine UI.

    Provides:
    - Show Merkle batch membership
    - Show inclusion proof
    - Show transparency log inclusion
    - Show regulator compliance status
    - Show SLA timing compliance
    """

    def __init__(self):
        """Initialize the batch view."""
        self._state: Optional[BatchViewState] = None

    @property
    def state(self) -> Optional[BatchViewState]:
        """Get current view state."""
        return self._state

    def load(
        self,
        execution_id: str,
        batch: Optional[ExecutionBatch] = None,
        batch_proof: Optional[BatchInclusionProof] = None,
        log_proof: Optional[LogInclusionProof] = None,
        checkpoint: Optional[TransparencyCheckpoint] = None,
        compliance_package: Optional[ComplianceProofPackage] = None,
    ) -> BatchViewState:
        """
        Load batch view data.

        Args:
            execution_id: Execution ID
            batch: Batch containing the execution
            batch_proof: Batch inclusion proof
            log_proof: Log inclusion proof
            checkpoint: Transparency checkpoint
            compliance_package: Compliance proof package

        Returns:
            BatchViewState
        """
        try:
            # Build batch membership info
            batch_membership = None
            if batch and batch.root:
                # Find leaf for this execution
                leaf = None
                for l in batch.leaves:
                    if l.execution_id == execution_id:
                        leaf = l
                        break

                if leaf:
                    batch_membership = BatchMembershipInfo(
                        batch_id=batch.batch_id,
                        batch_root_hash=batch.root.root_hash,
                        leaf_index=leaf.leaf_index,
                        leaf_count=batch.root.leaf_count,
                        gateway_id=batch.gateway_id,
                        created_at=batch.created_at,
                        sealed_at=batch.root.sealed_at,
                        has_proof=batch_proof is not None,
                    )

            # Build batch inclusion proof info
            batch_inclusion_proof_info = None
            if batch_proof:
                is_valid = batch_proof.verify()
                batch_inclusion_proof_info = InclusionProofInfo(
                    proof_type="batch",
                    is_valid=is_valid,
                    leaf_hash=batch_proof.leaf.leaf_hash,
                    root_hash=batch_proof.batch_root_hash,
                    proof_path_length=len(batch_proof.merkle_proof.proof_hashes),
                    verified_at=datetime.now(timezone.utc).isoformat(),
                )

            # Build transparency log info
            transparency_log = None
            if log_proof:
                transparency_log = TransparencyLogInfo(
                    log_id="primary",  # Would come from actual log
                    entry_index=log_proof.entry_index,
                    log_tree_size=log_proof.log_tree_size,
                    log_root_hash=log_proof.log_root_hash,
                    checkpoint_timestamp=(
                        checkpoint.timestamp if checkpoint else None
                    ),
                    has_proof=True,
                )

            # Build log inclusion proof info
            log_inclusion_proof_info = None
            if log_proof:
                is_valid = log_proof.verify()
                log_inclusion_proof_info = InclusionProofInfo(
                    proof_type="log",
                    is_valid=is_valid,
                    leaf_hash=log_proof.merkle_proof.leaf_hash,
                    root_hash=log_proof.log_root_hash,
                    proof_path_length=len(log_proof.merkle_proof.proof_hashes),
                    verified_at=datetime.now(timezone.utc).isoformat(),
                )

            # Build compliance info
            compliance = None
            if compliance_package:
                compliance = ComplianceInfo(
                    status=compliance_package.status,
                    jurisdiction_id=compliance_package.jurisdiction_id,
                    is_compliant=compliance_package.status == ComplianceStatus.COMPLIANT,
                    violations=compliance_package.violations,
                    proof_complete=compliance_package.is_complete(),
                    witness_count=len(compliance_package.witness_attestations),
                )

            # Build checkpoint dict
            checkpoint_dict = None
            if checkpoint:
                checkpoint_dict = checkpoint.to_dict()

            self._state = BatchViewState(
                execution_id=execution_id,
                batch_membership=batch_membership,
                batch_inclusion_proof=batch_inclusion_proof_info,
                transparency_log=transparency_log,
                log_inclusion_proof=log_inclusion_proof_info,
                compliance=compliance,
                checkpoint=checkpoint_dict,
            )

        except Exception as e:
            self._state = BatchViewState(
                execution_id=execution_id,
                error=str(e),
            )

        return self._state

    def verify_batch_proof(self) -> Optional[bool]:
        """
        Verify batch inclusion proof.

        Returns:
            True if valid, False if invalid, None if no proof
        """
        if self._state is None or self._state.batch_inclusion_proof is None:
            return None
        return self._state.batch_inclusion_proof.is_valid

    def verify_log_proof(self) -> Optional[bool]:
        """
        Verify log inclusion proof.

        Returns:
            True if valid, False if invalid, None if no proof
        """
        if self._state is None or self._state.log_inclusion_proof is None:
            return None
        return self._state.log_inclusion_proof.is_valid

    def get_verification_summary(self) -> Dict[str, Any]:
        """Get verification summary."""
        if self._state is None:
            return {}

        return {
            "hasBatch": self._state.batch_membership is not None,
            "batchProofValid": (
                self._state.batch_inclusion_proof.is_valid
                if self._state.batch_inclusion_proof else None
            ),
            "hasTransparencyLog": self._state.transparency_log is not None,
            "logProofValid": (
                self._state.log_inclusion_proof.is_valid
                if self._state.log_inclusion_proof else None
            ),
            "complianceStatus": (
                self._state.compliance.status.value
                if self._state.compliance else None
            ),
            "hasViolations": (
                len(self._state.compliance.violations) > 0
                if self._state.compliance else False
            ),
        }

    def get_sla_status(self) -> Optional[Dict[str, Any]]:
        """Get SLA timing status."""
        if self._state is None or self._state.compliance is None:
            return None

        violations = self._state.compliance.violations
        timing_violations = [
            v for v in violations
            if v.violation_type == "publication_delay"
        ]

        return {
            "hasTimingViolations": len(timing_violations) > 0,
            "violationCount": len(timing_violations),
            "violations": [v.to_dict() for v in timing_violations],
        }
