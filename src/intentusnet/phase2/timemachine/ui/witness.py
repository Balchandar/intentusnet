"""
Witness & Federation View (Time Machine UI - Phase II)

Provides visualization of witness attestations and federation state.

UI REQUIREMENTS:
- Show source gateway
- Show witness attestations
- Show verification scope per witness
- Show multi-witness quorum state
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from intentusnet.phase2.witness.attestation import (
    WitnessAttestation,
    WitnessScope,
    AttestationStatus,
    WitnessQuorum,
    QuorumState,
)
from intentusnet.phase2.federation.identity import (
    FederatedGatewayIdentity,
    TrustLevel,
)


# ===========================================================================
# Witness Entry
# ===========================================================================


@dataclass
class WitnessEntry:
    """
    A single witness attestation entry for display.

    Attributes:
        witness_id: ID of the witness
        attestation: The attestation record
        scopes_verified: Scopes this witness verified
        scope_results: Results per scope
        status: Attestation status
        trust_level: Trust level of the witness gateway
        is_selected: Whether this entry is selected
    """
    witness_id: str
    attestation: WitnessAttestation
    scopes_verified: List[WitnessScope]
    scope_results: Dict[str, bool]
    status: AttestationStatus
    trust_level: TrustLevel = TrustLevel.UNTRUSTED
    is_selected: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "witnessId": self.witness_id,
            "attestation": self.attestation.to_dict(),
            "scopesVerified": [s.value for s in self.scopes_verified],
            "scopeResults": self.scope_results,
            "status": self.status.value,
            "trustLevel": self.trust_level.value,
            "isSelected": self.is_selected,
        }


# ===========================================================================
# Gateway Info
# ===========================================================================


@dataclass
class GatewayInfo:
    """
    Gateway information for display.

    Attributes:
        gateway_id: Gateway identifier
        domain: Gateway domain
        trust_level: Trust level
        is_source: Whether this is the source gateway
        is_witness: Whether this gateway is a witness
    """
    gateway_id: str
    domain: Optional[str]
    trust_level: TrustLevel
    is_source: bool = False
    is_witness: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gatewayId": self.gateway_id,
            "domain": self.domain,
            "trustLevel": self.trust_level.value,
            "isSource": self.is_source,
            "isWitness": self.is_witness,
        }


# ===========================================================================
# Quorum Status
# ===========================================================================


@dataclass
class QuorumStatus:
    """
    Quorum status for display.

    Attributes:
        state: Current quorum state
        required_witnesses: Number of witnesses required
        current_witnesses: Number of witnesses received
        required_scopes: Scopes that must be verified
        covered_scopes: Scopes that have been verified
        missing_scopes: Scopes still needed
    """
    state: QuorumState
    required_witnesses: int
    current_witnesses: int
    required_scopes: Set[WitnessScope]
    covered_scopes: Set[WitnessScope]
    missing_scopes: Set[WitnessScope]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "requiredWitnesses": self.required_witnesses,
            "currentWitnesses": self.current_witnesses,
            "requiredScopes": [s.value for s in self.required_scopes],
            "coveredScopes": [s.value for s in self.covered_scopes],
            "missingScopes": [s.value for s in self.missing_scopes],
        }

    @property
    def progress_percent(self) -> float:
        """Get quorum progress as percentage."""
        if self.required_witnesses == 0:
            return 100.0
        return min(100.0, (self.current_witnesses / self.required_witnesses) * 100)


# ===========================================================================
# Witness View State
# ===========================================================================


@dataclass
class WitnessViewState:
    """
    State for the witness & federation view.

    Attributes:
        execution_id: Execution being viewed
        source_gateway: Source gateway info
        witness_entries: List of witness entries
        quorum_status: Current quorum status
        federated_gateways: List of federated gateways involved
        selected_witness_id: Currently selected witness
        loading: Whether data is loading
        error: Error message if loading failed
    """
    execution_id: str
    source_gateway: Optional[GatewayInfo] = None
    witness_entries: List[WitnessEntry] = field(default_factory=list)
    quorum_status: Optional[QuorumStatus] = None
    federated_gateways: List[GatewayInfo] = field(default_factory=list)
    selected_witness_id: Optional[str] = None
    loading: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "executionId": self.execution_id,
            "sourceGateway": self.source_gateway.to_dict() if self.source_gateway else None,
            "witnessEntries": [e.to_dict() for e in self.witness_entries],
            "quorumStatus": self.quorum_status.to_dict() if self.quorum_status else None,
            "federatedGateways": [g.to_dict() for g in self.federated_gateways],
            "selectedWitnessId": self.selected_witness_id,
            "loading": self.loading,
            "error": self.error,
        }


# ===========================================================================
# Witness View
# ===========================================================================


class WitnessView:
    """
    Witness & Federation view controller for the Time Machine UI.

    Provides:
    - Show source gateway
    - Show witness attestations
    - Show verification scope per witness
    - Show multi-witness quorum state
    """

    def __init__(self):
        """Initialize the witness view."""
        self._state: Optional[WitnessViewState] = None

    @property
    def state(self) -> Optional[WitnessViewState]:
        """Get current view state."""
        return self._state

    def load(
        self,
        execution_id: str,
        source_gateway_id: str,
        attestations: List[WitnessAttestation],
        quorum: Optional[WitnessQuorum] = None,
        gateway_identities: Optional[Dict[str, FederatedGatewayIdentity]] = None,
    ) -> WitnessViewState:
        """
        Load witness view data.

        Args:
            execution_id: Execution ID
            source_gateway_id: ID of the source gateway
            attestations: List of witness attestations
            quorum: Optional quorum information
            gateway_identities: Optional map of gateway identities

        Returns:
            WitnessViewState
        """
        gateway_identities = gateway_identities or {}

        try:
            # Build source gateway info
            source_identity = gateway_identities.get(source_gateway_id)
            source_gateway = GatewayInfo(
                gateway_id=source_gateway_id,
                domain=source_identity.domain if source_identity else None,
                trust_level=source_identity.trust_level if source_identity else TrustLevel.UNTRUSTED,
                is_source=True,
            )

            # Build witness entries
            witness_entries: List[WitnessEntry] = []
            for attestation in attestations:
                witness_identity = gateway_identities.get(attestation.witness_id)
                entry = WitnessEntry(
                    witness_id=attestation.witness_id,
                    attestation=attestation,
                    scopes_verified=attestation.scopes_verified,
                    scope_results=attestation.scope_results,
                    status=attestation.status,
                    trust_level=(
                        witness_identity.trust_level
                        if witness_identity else TrustLevel.UNTRUSTED
                    ),
                )
                witness_entries.append(entry)

            # Build quorum status
            quorum_status = None
            if quorum:
                quorum_status = QuorumStatus(
                    state=quorum.state,
                    required_witnesses=quorum.required_witnesses,
                    current_witnesses=len(quorum.attestations),
                    required_scopes=quorum.required_scopes,
                    covered_scopes=self._get_covered_scopes(quorum.attestations),
                    missing_scopes=quorum.get_missing_scopes(),
                )

            # Build federated gateways list
            federated_gateways: List[GatewayInfo] = []
            seen_ids: Set[str] = {source_gateway_id}

            for attestation in attestations:
                if attestation.witness_id not in seen_ids:
                    identity = gateway_identities.get(attestation.witness_id)
                    federated_gateways.append(GatewayInfo(
                        gateway_id=attestation.witness_id,
                        domain=identity.domain if identity else None,
                        trust_level=(
                            identity.trust_level if identity else TrustLevel.UNTRUSTED
                        ),
                        is_witness=True,
                    ))
                    seen_ids.add(attestation.witness_id)

            self._state = WitnessViewState(
                execution_id=execution_id,
                source_gateway=source_gateway,
                witness_entries=witness_entries,
                quorum_status=quorum_status,
                federated_gateways=federated_gateways,
            )

        except Exception as e:
            self._state = WitnessViewState(
                execution_id=execution_id,
                error=str(e),
            )

        return self._state

    def _get_covered_scopes(
        self,
        attestations: List[WitnessAttestation],
    ) -> Set[WitnessScope]:
        """Get all scopes covered by attestations."""
        covered: Set[WitnessScope] = set()
        for attestation in attestations:
            if attestation.status == AttestationStatus.VALID:
                for scope in attestation.scopes_verified:
                    if attestation.scope_results.get(scope.value, False):
                        covered.add(scope)
        return covered

    def select_witness(self, witness_id: str) -> None:
        """Select a witness entry."""
        if self._state is None:
            return

        self._state.selected_witness_id = witness_id

        for entry in self._state.witness_entries:
            entry.is_selected = entry.witness_id == witness_id

    def get_scope_coverage(self) -> Dict[str, Dict[str, Any]]:
        """
        Get scope coverage summary.

        Returns:
            Dict mapping scope to coverage info
        """
        if self._state is None:
            return {}

        coverage: Dict[str, Dict[str, Any]] = {}

        for scope in WitnessScope:
            verifying_witnesses: List[str] = []
            passing_witnesses: List[str] = []

            for entry in self._state.witness_entries:
                if scope in entry.scopes_verified:
                    verifying_witnesses.append(entry.witness_id)
                    if entry.scope_results.get(scope.value, False):
                        passing_witnesses.append(entry.witness_id)

            coverage[scope.value] = {
                "verifyingWitnesses": verifying_witnesses,
                "passingWitnesses": passing_witnesses,
                "verified": len(passing_witnesses) > 0,
            }

        return coverage

    def get_witness_summary(self) -> Dict[str, Any]:
        """Get witness summary statistics."""
        if self._state is None:
            return {}

        total = len(self._state.witness_entries)
        valid = sum(
            1 for e in self._state.witness_entries
            if e.status == AttestationStatus.VALID
        )
        partial = sum(
            1 for e in self._state.witness_entries
            if e.status == AttestationStatus.PARTIAL
        )
        invalid = sum(
            1 for e in self._state.witness_entries
            if e.status == AttestationStatus.INVALID
        )

        return {
            "totalWitnesses": total,
            "validAttestations": valid,
            "partialAttestations": partial,
            "invalidAttestations": invalid,
            "quorumMet": (
                self._state.quorum_status.state == QuorumState.MET
                if self._state.quorum_status else None
            ),
        }
