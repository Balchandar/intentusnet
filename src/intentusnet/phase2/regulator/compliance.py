"""
Regulator-Operated Transparency Logs (Phase II)

Provides jurisdiction-specific compliance enforcement and proofs.

Key concepts:
- Mandatory publication enforcement
- Jurisdiction-based policies
- Time-bound publication SLAs
- Witness quorum requirements
- Compliance proof packages
- Optional external time anchoring
- NO payload access for regulators (privacy-preserving)

CRITICAL INVARIANTS:
1. Regulators NEVER have access to decrypted payloads
2. All compliance proofs are based on hashes and signatures
3. Publication SLAs are enforced automatically
4. Compliance status is publicly verifiable
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from intentusnet.phase2.merkle.batch import (
    BatchRoot,
    BatchInclusionProof,
)
from intentusnet.phase2.transparency.log import (
    TransparencyCheckpoint,
    LogInclusionProof,
)
from intentusnet.phase2.witness.attestation import WitnessAttestation


# ===========================================================================
# Compliance Status
# ===========================================================================


class ComplianceStatus(Enum):
    """Compliance status for an execution or batch."""
    COMPLIANT = "compliant"  # All requirements met
    PENDING = "pending"  # Awaiting publication or attestation
    VIOLATION = "violation"  # SLA or requirement violated
    EXEMPT = "exempt"  # Exempt from compliance requirements
    UNKNOWN = "unknown"  # Status cannot be determined


# ===========================================================================
# SLA Violation
# ===========================================================================


@dataclass
class SLAViolation:
    """
    Record of an SLA violation.

    Attributes:
        violation_id: Unique identifier
        batch_id: ID of the batch that violated
        violation_type: Type of violation
        expected_deadline: When the SLA required completion
        actual_time: When compliance was achieved (if ever)
        severity: Severity level (minor, major, critical)
        details: Additional violation details
    """
    violation_id: str
    batch_id: str
    violation_type: str
    expected_deadline: str
    actual_time: Optional[str] = None
    severity: str = "major"
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "violationId": self.violation_id,
            "batchId": self.batch_id,
            "violationType": self.violation_type,
            "expectedDeadline": self.expected_deadline,
            "actualTime": self.actual_time,
            "severity": self.severity,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SLAViolation":
        return cls(
            violation_id=data["violationId"],
            batch_id=data["batchId"],
            violation_type=data["violationType"],
            expected_deadline=data["expectedDeadline"],
            actual_time=data.get("actualTime"),
            severity=data.get("severity", "major"),
            details=data.get("details", {}),
        )


# ===========================================================================
# Time Anchor
# ===========================================================================


@dataclass
class TimeAnchor:
    """
    External time anchor for compliance timestamping.

    Time anchors provide trusted timestamps from external sources
    (e.g., RFC 3161 timestamp authority, blockchain).

    Attributes:
        anchor_id: Unique identifier
        anchor_type: Type of anchor (rfc3161, blockchain, etc.)
        anchor_time: Timestamp from the anchor
        anchor_proof: Proof data from the anchor
        anchored_hash: Hash that was anchored
        source: Source of the anchor (URL, chain ID, etc.)
    """
    anchor_id: str
    anchor_type: str
    anchor_time: str
    anchor_proof: str  # Base64 or hex encoded
    anchored_hash: str
    source: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anchorId": self.anchor_id,
            "anchorType": self.anchor_type,
            "anchorTime": self.anchor_time,
            "anchorProof": self.anchor_proof,
            "anchoredHash": self.anchored_hash,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimeAnchor":
        return cls(
            anchor_id=data["anchorId"],
            anchor_type=data["anchorType"],
            anchor_time=data["anchorTime"],
            anchor_proof=data["anchorProof"],
            anchored_hash=data["anchoredHash"],
            source=data["source"],
        )


# ===========================================================================
# Publication SLA
# ===========================================================================


@dataclass
class PublicationSLA:
    """
    Service Level Agreement for publication timing.

    Attributes:
        sla_id: Unique identifier
        name: Human-readable name
        max_batch_delay_seconds: Max time from batch creation to publication
        max_checkpoint_interval_seconds: Max time between checkpoints
        min_witnesses_required: Minimum witness attestations
        require_time_anchor: Whether external time anchor is required
    """
    sla_id: str
    name: str
    max_batch_delay_seconds: int = 3600  # 1 hour
    max_checkpoint_interval_seconds: int = 86400  # 24 hours
    min_witnesses_required: int = 0
    require_time_anchor: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slaId": self.sla_id,
            "name": self.name,
            "maxBatchDelaySeconds": self.max_batch_delay_seconds,
            "maxCheckpointIntervalSeconds": self.max_checkpoint_interval_seconds,
            "minWitnessesRequired": self.min_witnesses_required,
            "requireTimeAnchor": self.require_time_anchor,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PublicationSLA":
        return cls(
            sla_id=data["slaId"],
            name=data["name"],
            max_batch_delay_seconds=data.get("maxBatchDelaySeconds", 3600),
            max_checkpoint_interval_seconds=data.get("maxCheckpointIntervalSeconds", 86400),
            min_witnesses_required=data.get("minWitnessesRequired", 0),
            require_time_anchor=data.get("requireTimeAnchor", False),
        )

    def check_batch_timing(self, batch_created: str, published_at: str) -> Optional[str]:
        """
        Check if batch was published within SLA.

        Returns:
            None if compliant, error message if violated
        """
        from dateutil.parser import isoparse

        try:
            created = isoparse(batch_created)
            published = isoparse(published_at)
            delay = (published - created).total_seconds()

            if delay > self.max_batch_delay_seconds:
                return (
                    f"Batch published {delay:.0f}s after creation, "
                    f"exceeds SLA of {self.max_batch_delay_seconds}s"
                )
            return None
        except Exception as e:
            return f"Failed to parse timestamps: {e}"


# ===========================================================================
# Jurisdiction Policy
# ===========================================================================


@dataclass
class JurisdictionPolicy:
    """
    Compliance policy for a specific jurisdiction.

    Attributes:
        jurisdiction_id: Unique identifier (e.g., "US", "EU", "UK")
        name: Human-readable name
        publication_sla: Publication timing requirements
        required_witness_count: Number of witnesses required
        allowed_gateway_domains: Domains allowed to serve this jurisdiction
        requires_regulator_log: Whether regulator-operated log is required
        retention_period_days: How long records must be retained
        intent_overrides: Per-intent policy overrides
    """
    jurisdiction_id: str
    name: str
    publication_sla: PublicationSLA
    required_witness_count: int = 1
    allowed_gateway_domains: Set[str] = field(default_factory=set)
    requires_regulator_log: bool = True
    retention_period_days: int = 2555  # ~7 years
    intent_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "jurisdictionId": self.jurisdiction_id,
            "name": self.name,
            "publicationSla": self.publication_sla.to_dict(),
            "requiredWitnessCount": self.required_witness_count,
            "allowedGatewayDomains": list(self.allowed_gateway_domains),
            "requiresRegulatorLog": self.requires_regulator_log,
            "retentionPeriodDays": self.retention_period_days,
            "intentOverrides": self.intent_overrides,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JurisdictionPolicy":
        return cls(
            jurisdiction_id=data["jurisdictionId"],
            name=data["name"],
            publication_sla=PublicationSLA.from_dict(data["publicationSla"]),
            required_witness_count=data.get("requiredWitnessCount", 1),
            allowed_gateway_domains=set(data.get("allowedGatewayDomains", [])),
            requires_regulator_log=data.get("requiresRegulatorLog", True),
            retention_period_days=data.get("retentionPeriodDays", 2555),
            intent_overrides=data.get("intentOverrides", {}),
        )

    def get_witness_requirement(self, intent_name: str) -> int:
        """Get witness requirement for an intent."""
        override = self.intent_overrides.get(intent_name)
        if override and "required_witness_count" in override:
            return override["required_witness_count"]
        return self.required_witness_count


# ===========================================================================
# Compliance Proof Package
# ===========================================================================


@dataclass
class ComplianceProofPackage:
    """
    Complete proof package for regulatory compliance.

    This package contains all proofs needed to demonstrate compliance,
    WITHOUT including any decrypted payload data.

    CRITICAL: This package NEVER contains plaintext payloads.

    Attributes:
        package_id: Unique identifier
        execution_id: ID of the execution
        canonical_hash: Hash of the execution
        batch_id: ID of the containing batch
        jurisdiction_id: Applicable jurisdiction
        status: Compliance status
        batch_inclusion_proof: Proof of batch membership
        log_inclusion_proof: Proof of transparency log membership
        witness_attestations: Collected witness attestations
        time_anchor: Optional external time anchor
        checkpoint: Transparency checkpoint
        violations: List of SLA violations (if any)
        created_at: When this package was created
    """
    package_id: str
    execution_id: str
    canonical_hash: str
    batch_id: str
    jurisdiction_id: str
    status: ComplianceStatus
    batch_inclusion_proof: Optional[BatchInclusionProof] = None
    log_inclusion_proof: Optional[LogInclusionProof] = None
    witness_attestations: List[WitnessAttestation] = field(default_factory=list)
    time_anchor: Optional[TimeAnchor] = None
    checkpoint: Optional[TransparencyCheckpoint] = None
    violations: List[SLAViolation] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "packageId": self.package_id,
            "executionId": self.execution_id,
            "canonicalHash": self.canonical_hash,
            "batchId": self.batch_id,
            "jurisdictionId": self.jurisdiction_id,
            "status": self.status.value,
            "batchInclusionProof": (
                self.batch_inclusion_proof.to_dict()
                if self.batch_inclusion_proof else None
            ),
            "logInclusionProof": (
                self.log_inclusion_proof.to_dict()
                if self.log_inclusion_proof else None
            ),
            "witnessAttestations": [a.to_dict() for a in self.witness_attestations],
            "timeAnchor": self.time_anchor.to_dict() if self.time_anchor else None,
            "checkpoint": self.checkpoint.to_dict() if self.checkpoint else None,
            "violations": [v.to_dict() for v in self.violations],
            "createdAt": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ComplianceProofPackage":
        bip_data = data.get("batchInclusionProof")
        lip_data = data.get("logInclusionProof")
        ta_data = data.get("timeAnchor")
        cp_data = data.get("checkpoint")

        return cls(
            package_id=data["packageId"],
            execution_id=data["executionId"],
            canonical_hash=data["canonicalHash"],
            batch_id=data["batchId"],
            jurisdiction_id=data["jurisdictionId"],
            status=ComplianceStatus(data["status"]),
            batch_inclusion_proof=(
                BatchInclusionProof.from_dict(bip_data) if bip_data else None
            ),
            log_inclusion_proof=(
                LogInclusionProof.from_dict(lip_data) if lip_data else None
            ),
            witness_attestations=[
                WitnessAttestation.from_dict(a)
                for a in data.get("witnessAttestations", [])
            ],
            time_anchor=TimeAnchor.from_dict(ta_data) if ta_data else None,
            checkpoint=(
                TransparencyCheckpoint.from_dict(cp_data) if cp_data else None
            ),
            violations=[
                SLAViolation.from_dict(v) for v in data.get("violations", [])
            ],
            created_at=data.get("createdAt", datetime.now(timezone.utc).isoformat()),
        )

    def compute_package_hash(self) -> str:
        """Compute hash of the proof package."""
        content = {
            "packageId": self.package_id,
            "executionId": self.execution_id,
            "canonicalHash": self.canonical_hash,
            "batchId": self.batch_id,
            "jurisdictionId": self.jurisdiction_id,
            "status": self.status.value,
        }
        canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def is_complete(self) -> bool:
        """Check if the proof package has all required components."""
        return (
            self.batch_inclusion_proof is not None
            and self.log_inclusion_proof is not None
            and self.checkpoint is not None
        )

    def verify_all_proofs(self) -> Dict[str, bool]:
        """
        Verify all proofs in the package.

        Returns:
            Dict mapping proof name to verification result
        """
        results: Dict[str, bool] = {}

        if self.batch_inclusion_proof:
            results["batchInclusion"] = self.batch_inclusion_proof.verify()
        else:
            results["batchInclusion"] = False

        if self.log_inclusion_proof:
            results["logInclusion"] = self.log_inclusion_proof.verify()
        else:
            results["logInclusion"] = False

        return results


# ===========================================================================
# Regulator Transparency Log
# ===========================================================================


class RegulatorTransparencyLog:
    """
    Regulator-operated transparency log.

    This is a specialized transparency log operated by or for regulators.
    It enforces jurisdiction-specific compliance requirements.

    CRITICAL: This log has NO access to decrypted payloads.
    It only stores and verifies hashes, signatures, and proofs.
    """

    def __init__(
        self,
        log_id: str,
        jurisdiction_policy: JurisdictionPolicy,
    ):
        """
        Initialize a regulator transparency log.

        Args:
            log_id: Unique identifier for this log
            jurisdiction_policy: Compliance policy for this jurisdiction
        """
        self._log_id = log_id
        self._policy = jurisdiction_policy

        # Internal state
        self._batches: Dict[str, BatchRoot] = {}
        self._compliance_packages: Dict[str, ComplianceProofPackage] = {}
        self._violations: List[SLAViolation] = []
        self._pending_batches: Dict[str, str] = {}  # batch_id -> created_at

    @property
    def log_id(self) -> str:
        return self._log_id

    @property
    def jurisdiction(self) -> JurisdictionPolicy:
        return self._policy

    def register_batch(self, batch_root: BatchRoot) -> ComplianceStatus:
        """
        Register a batch for compliance tracking.

        Args:
            batch_root: The batch root to register

        Returns:
            Initial compliance status
        """
        if batch_root.batch_id in self._batches:
            return ComplianceStatus.COMPLIANT

        self._batches[batch_root.batch_id] = batch_root
        self._pending_batches[batch_root.batch_id] = batch_root.created_at

        # Check SLA timing
        now = datetime.now(timezone.utc).isoformat()
        timing_error = self._policy.publication_sla.check_batch_timing(
            batch_root.created_at, now
        )

        if timing_error:
            violation = SLAViolation(
                violation_id=f"sla-{batch_root.batch_id[:8]}",
                batch_id=batch_root.batch_id,
                violation_type="publication_delay",
                expected_deadline=self._compute_deadline(batch_root.created_at),
                actual_time=now,
                severity="major",
                details={"error": timing_error},
            )
            self._violations.append(violation)
            return ComplianceStatus.VIOLATION

        return ComplianceStatus.PENDING

    def _compute_deadline(self, created_at: str) -> str:
        """Compute publication deadline from creation time."""
        from dateutil.parser import isoparse

        try:
            created = isoparse(created_at)
            deadline = created + timedelta(
                seconds=self._policy.publication_sla.max_batch_delay_seconds
            )
            return deadline.isoformat()
        except Exception:
            return created_at

    def record_witness_attestation(
        self,
        batch_id: str,
        attestation: WitnessAttestation,
    ) -> None:
        """Record a witness attestation for a batch."""
        if batch_id not in self._compliance_packages:
            # Create initial package
            batch_root = self._batches.get(batch_id)
            if batch_root is None:
                return

            import uuid
            package = ComplianceProofPackage(
                package_id=str(uuid.uuid4()),
                execution_id="",  # Will be filled per-execution
                canonical_hash="",
                batch_id=batch_id,
                jurisdiction_id=self._policy.jurisdiction_id,
                status=ComplianceStatus.PENDING,
            )
            self._compliance_packages[batch_id] = package

        self._compliance_packages[batch_id].witness_attestations.append(attestation)

    def check_batch_compliance(self, batch_id: str) -> ComplianceStatus:
        """
        Check compliance status of a batch.

        Args:
            batch_id: ID of the batch

        Returns:
            Current compliance status
        """
        if batch_id not in self._batches:
            return ComplianceStatus.UNKNOWN

        batch_root = self._batches[batch_id]

        # Check witness count
        package = self._compliance_packages.get(batch_id)
        witness_count = len(package.witness_attestations) if package else 0

        if witness_count < self._policy.required_witness_count:
            return ComplianceStatus.PENDING

        # Check for existing violations
        for violation in self._violations:
            if violation.batch_id == batch_id:
                return ComplianceStatus.VIOLATION

        return ComplianceStatus.COMPLIANT

    def generate_compliance_package(
        self,
        execution_id: str,
        canonical_hash: str,
        batch_id: str,
        batch_inclusion_proof: BatchInclusionProof,
        log_inclusion_proof: Optional[LogInclusionProof] = None,
        checkpoint: Optional[TransparencyCheckpoint] = None,
        time_anchor: Optional[TimeAnchor] = None,
    ) -> ComplianceProofPackage:
        """
        Generate a complete compliance proof package.

        Args:
            execution_id: ID of the execution
            canonical_hash: Canonical hash of the execution
            batch_id: ID of the containing batch
            batch_inclusion_proof: Proof of batch membership
            log_inclusion_proof: Proof of log membership
            checkpoint: Transparency checkpoint
            time_anchor: Optional time anchor

        Returns:
            ComplianceProofPackage
        """
        import uuid

        # Collect witness attestations for this batch
        attestations = []
        if batch_id in self._compliance_packages:
            attestations = self._compliance_packages[batch_id].witness_attestations

        # Collect violations
        violations = [v for v in self._violations if v.batch_id == batch_id]

        # Determine status
        if violations:
            status = ComplianceStatus.VIOLATION
        elif len(attestations) < self._policy.required_witness_count:
            status = ComplianceStatus.PENDING
        elif log_inclusion_proof is None and self._policy.requires_regulator_log:
            status = ComplianceStatus.PENDING
        else:
            status = ComplianceStatus.COMPLIANT

        return ComplianceProofPackage(
            package_id=str(uuid.uuid4()),
            execution_id=execution_id,
            canonical_hash=canonical_hash,
            batch_id=batch_id,
            jurisdiction_id=self._policy.jurisdiction_id,
            status=status,
            batch_inclusion_proof=batch_inclusion_proof,
            log_inclusion_proof=log_inclusion_proof,
            witness_attestations=attestations,
            time_anchor=time_anchor,
            checkpoint=checkpoint,
            violations=violations,
        )

    def get_violations(
        self,
        batch_id: Optional[str] = None,
    ) -> List[SLAViolation]:
        """Get SLA violations, optionally filtered by batch."""
        if batch_id:
            return [v for v in self._violations if v.batch_id == batch_id]
        return list(self._violations)

    def get_compliance_status_report(self) -> Dict[str, Any]:
        """
        Generate a compliance status report.

        Returns:
            Report with summary statistics and details
        """
        total_batches = len(self._batches)
        compliant_count = sum(
            1 for bid in self._batches
            if self.check_batch_compliance(bid) == ComplianceStatus.COMPLIANT
        )
        pending_count = sum(
            1 for bid in self._batches
            if self.check_batch_compliance(bid) == ComplianceStatus.PENDING
        )
        violation_count = len(self._violations)

        return {
            "logId": self._log_id,
            "jurisdictionId": self._policy.jurisdiction_id,
            "totalBatches": total_batches,
            "compliantBatches": compliant_count,
            "pendingBatches": pending_count,
            "totalViolations": violation_count,
            "reportGeneratedAt": datetime.now(timezone.utc).isoformat(),
        }
