"""
Execution Detail View (Time Machine UI - Phase II)

Provides detailed execution view with tabs for different sections.

UI REQUIREMENTS:
- Tabs: Summary, Input, Output, Trace, Diff, Metadata, Witnesses, Batches, Compliance
- Verification status always shown first
- Signature MUST verify before rendering content
- Encryption state clearly shown per section
- Decryption must be explicit and user-triggered
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from intentusnet.phase2.timemachine.api.core import (
    TimeMachineAPI,
    ExecutionQuery,
    ExecutionDetailResponse,
    VerificationStatus,
    SectionContent,
)
from intentusnet.phase2.gateway.encryption import SectionType, ExecutionDEK


# ===========================================================================
# Detail View Tabs
# ===========================================================================


class DetailTab(Enum):
    """Available tabs in the execution detail view."""
    SUMMARY = "summary"
    INPUT = "input"
    OUTPUT = "output"
    TRACE = "trace"
    DIFF = "diff"
    METADATA = "metadata"
    WITNESSES = "witnesses"
    BATCHES = "batches"
    COMPLIANCE = "compliance"


# ===========================================================================
# Section View State
# ===========================================================================


class EncryptionState(Enum):
    """Visual encryption state for a section."""
    ENCRYPTED = "encrypted"  # Section is encrypted, not decrypted
    DECRYPTED = "decrypted"  # Section was decrypted
    PLAINTEXT = "plaintext"  # Section was never encrypted
    ERROR = "error"  # Decryption failed


@dataclass
class SectionViewState:
    """
    View state for a content section.

    Attributes:
        section_type: Type of section
        encryption_state: Current encryption state
        content: Section content (None if encrypted and not decrypted)
        can_decrypt: Whether decryption is possible
        decryption_error: Error message if decryption failed
        is_loading: Whether decryption is in progress
    """
    section_type: SectionType
    encryption_state: EncryptionState
    content: Optional[Dict[str, Any]] = None
    can_decrypt: bool = False
    decryption_error: Optional[str] = None
    is_loading: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sectionType": self.section_type.value,
            "encryptionState": self.encryption_state.value,
            "content": self.content,
            "canDecrypt": self.can_decrypt,
            "decryptionError": self.decryption_error,
            "isLoading": self.is_loading,
        }


# ===========================================================================
# Verification Banner
# ===========================================================================


@dataclass
class VerificationBanner:
    """
    Verification status banner - ALWAYS shown first.

    Attributes:
        status: Overall verification status
        signature_verified: Whether signature was verified
        hash_verified: Whether hash was verified
        message: Human-readable status message
        severity: Visual severity (success, warning, error)
    """
    status: VerificationStatus
    signature_verified: bool
    hash_verified: bool
    message: str
    severity: str  # "success", "warning", "error"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "signatureVerified": self.signature_verified,
            "hashVerified": self.hash_verified,
            "message": self.message,
            "severity": self.severity,
        }

    @classmethod
    def from_verification(
        cls,
        status: VerificationStatus,
        signature_verified: bool,
        hash_verified: bool,
    ) -> "VerificationBanner":
        """Create banner from verification results."""
        if status == VerificationStatus.VERIFIED:
            return cls(
                status=status,
                signature_verified=signature_verified,
                hash_verified=hash_verified,
                message="Execution verified: signature and hash are valid",
                severity="success",
            )
        elif status == VerificationStatus.PARTIAL:
            parts = []
            if signature_verified:
                parts.append("signature valid")
            else:
                parts.append("signature INVALID")
            if hash_verified:
                parts.append("hash valid")
            else:
                parts.append("hash INVALID")
            return cls(
                status=status,
                signature_verified=signature_verified,
                hash_verified=hash_verified,
                message=f"Partial verification: {', '.join(parts)}",
                severity="warning",
            )
        else:
            return cls(
                status=status,
                signature_verified=signature_verified,
                hash_verified=hash_verified,
                message="VERIFICATION FAILED: Content may be tampered",
                severity="error",
            )


# ===========================================================================
# Execution Detail View State
# ===========================================================================


@dataclass
class ExecutionDetailViewState:
    """
    State for the execution detail view.

    Attributes:
        execution_id: Execution being viewed
        detail: Full execution detail response
        verification_banner: ALWAYS shown first
        active_tab: Currently active tab
        input_section: Input section state
        output_section: Output section state
        trace_section: Trace section state
        loading: Whether detail is loading
        error: Error message if loading failed
    """
    execution_id: str
    detail: Optional[ExecutionDetailResponse]
    verification_banner: Optional[VerificationBanner]
    active_tab: DetailTab
    input_section: Optional[SectionViewState] = None
    output_section: Optional[SectionViewState] = None
    trace_section: Optional[SectionViewState] = None
    loading: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "executionId": self.execution_id,
            "detail": self.detail.to_dict() if self.detail else None,
            "verificationBanner": (
                self.verification_banner.to_dict()
                if self.verification_banner else None
            ),
            "activeTab": self.active_tab.value,
            "inputSection": self.input_section.to_dict() if self.input_section else None,
            "outputSection": self.output_section.to_dict() if self.output_section else None,
            "traceSection": self.trace_section.to_dict() if self.trace_section else None,
            "loading": self.loading,
            "error": self.error,
        }


# ===========================================================================
# Execution Detail View
# ===========================================================================


class ExecutionDetailView:
    """
    Execution detail view controller for the Time Machine UI.

    CRITICAL CONSTRAINTS:
    - Verification status ALWAYS shown first
    - Signature MUST verify before rendering content
    - Encryption state clearly shown per section
    - Decryption must be explicit and user-triggered
    """

    def __init__(self, api: TimeMachineAPI):
        """
        Initialize the execution detail view.

        Args:
            api: Time Machine API instance
        """
        self._api = api
        self._state: Optional[ExecutionDetailViewState] = None

    @property
    def state(self) -> Optional[ExecutionDetailViewState]:
        """Get current view state."""
        return self._state

    def load(self, execution_id: str) -> ExecutionDetailViewState:
        """
        Load execution detail.

        CRITICAL: Verification status is determined first.

        Args:
            execution_id: Execution to load

        Returns:
            ExecutionDetailViewState
        """
        query = ExecutionQuery(
            execution_id=execution_id,
            verify_signature=True,
        )

        try:
            detail = self._api.get_execution_detail(query)

            if detail is None:
                self._state = ExecutionDetailViewState(
                    execution_id=execution_id,
                    detail=None,
                    verification_banner=None,
                    active_tab=DetailTab.SUMMARY,
                    error="Execution not found",
                )
                return self._state

            # Create verification banner FIRST
            verification_banner = VerificationBanner.from_verification(
                status=detail.verification_status,
                signature_verified=detail.signature_verified,
                hash_verified=detail.hash_verified,
            )

            # Create section view states
            input_section = self._create_section_state(
                detail.input_section,
                SectionType.INPUT,
            )
            output_section = self._create_section_state(
                detail.output_section,
                SectionType.OUTPUT,
            )
            trace_section = self._create_section_state(
                detail.trace_section,
                SectionType.TRACE,
            )

            self._state = ExecutionDetailViewState(
                execution_id=execution_id,
                detail=detail,
                verification_banner=verification_banner,
                active_tab=DetailTab.SUMMARY,
                input_section=input_section,
                output_section=output_section,
                trace_section=trace_section,
            )

        except Exception as e:
            self._state = ExecutionDetailViewState(
                execution_id=execution_id,
                detail=None,
                verification_banner=None,
                active_tab=DetailTab.SUMMARY,
                error=str(e),
            )

        return self._state

    def _create_section_state(
        self,
        section: SectionContent,
        section_type: SectionType,
    ) -> SectionViewState:
        """Create section view state from content."""
        if section.is_encrypted:
            if section.decryption_error:
                encryption_state = EncryptionState.ERROR
            else:
                encryption_state = EncryptionState.ENCRYPTED
        else:
            encryption_state = EncryptionState.PLAINTEXT

        return SectionViewState(
            section_type=section_type,
            encryption_state=encryption_state,
            content=section.content,
            can_decrypt=section.is_encrypted and section.content is None,
            decryption_error=section.decryption_error,
        )

    def switch_tab(self, tab: DetailTab) -> None:
        """Switch to a different tab."""
        if self._state:
            self._state.active_tab = tab

    def request_decryption(
        self,
        section_type: SectionType,
        dek: ExecutionDEK,
    ) -> SectionViewState:
        """
        Request decryption of a section.

        CRITICAL: This is EXPLICIT user-triggered decryption.

        Args:
            section_type: Section to decrypt
            dek: Data encryption key

        Returns:
            Updated SectionViewState
        """
        if self._state is None or self._state.detail is None:
            return SectionViewState(
                section_type=section_type,
                encryption_state=EncryptionState.ERROR,
                decryption_error="No execution loaded",
            )

        # CRITICAL: Check verification before allowing decryption
        if self._state.detail.verification_status == VerificationStatus.FAILED:
            return SectionViewState(
                section_type=section_type,
                encryption_state=EncryptionState.ERROR,
                decryption_error="DECRYPTION BLOCKED: Verification failed",
            )

        # Get appropriate section state
        section_state = self._get_section_state(section_type)
        if section_state is None:
            return SectionViewState(
                section_type=section_type,
                encryption_state=EncryptionState.ERROR,
                decryption_error="Section not found",
            )

        # Mark as loading
        section_state.is_loading = True

        # Request decryption from API
        result = self._api.request_decryption(
            execution_id=self._state.execution_id,
            section_type=section_type,
            dek=dek,
        )

        # Update section state
        if result.success:
            section_state.encryption_state = EncryptionState.DECRYPTED
            section_state.content = result.plaintext
            section_state.decryption_error = None
        else:
            section_state.encryption_state = EncryptionState.ERROR
            section_state.decryption_error = result.error

        section_state.is_loading = False
        section_state.can_decrypt = False

        return section_state

    def _get_section_state(
        self,
        section_type: SectionType,
    ) -> Optional[SectionViewState]:
        """Get section state by type."""
        if self._state is None:
            return None

        if section_type == SectionType.INPUT:
            return self._state.input_section
        elif section_type == SectionType.OUTPUT:
            return self._state.output_section
        elif section_type == SectionType.TRACE:
            return self._state.trace_section
        return None

    def get_available_tabs(self) -> List[DetailTab]:
        """
        Get available tabs based on execution data.

        Returns:
            List of available tabs
        """
        tabs = [DetailTab.SUMMARY]

        if self._state and self._state.detail:
            # Always include these
            tabs.append(DetailTab.INPUT)
            tabs.append(DetailTab.OUTPUT)
            tabs.append(DetailTab.METADATA)

            # Trace if present
            if self._state.detail.trace_section.content is not None:
                tabs.append(DetailTab.TRACE)

            # Witnesses if present
            if self._state.detail.witness_attestations:
                tabs.append(DetailTab.WITNESSES)

            # Batches if present
            if self._state.detail.batch_membership:
                tabs.append(DetailTab.BATCHES)

            # Compliance if status available
            if self._state.detail.compliance_status:
                tabs.append(DetailTab.COMPLIANCE)

            # Diff always available for comparison
            tabs.append(DetailTab.DIFF)

        return tabs

    def get_summary_data(self) -> Optional[Dict[str, Any]]:
        """
        Get summary data for the summary tab.

        Returns:
            Dict with summary information
        """
        if self._state is None or self._state.detail is None:
            return None

        detail = self._state.detail

        return {
            "executionId": detail.execution_id,
            "canonicalHash": detail.canonical_hash,
            "gatewayId": detail.gateway_id,
            "createdAt": detail.created_at,
            "intentName": detail.intent_name,
            "intentVersion": detail.intent_version,
            "verificationStatus": detail.verification_status.value,
            "hasParent": detail.parent_execution_hash is not None,
            "parentExecutionHash": detail.parent_execution_hash,
            "witnessCount": len(detail.witness_attestations),
            "isBatched": detail.batch_membership is not None,
            "encryptedSections": {
                "input": detail.input_section.is_encrypted,
                "output": detail.output_section.is_encrypted,
                "trace": detail.trace_section.is_encrypted,
            },
        }
