"""
IntentusNet Phase II: Enforcement, Federation, Proofs, and Time Machine UI

This module implements the complete Phase II specification:

A. CORE BACKEND / PROTOCOL:
   1. Gateway Enforcement - Root of trust, canonical execution construction
   2. EMCL Encrypted Execution Payloads - Section-level encryption with AAD binding
   3. Gateway Federation - Cross-gateway verification and attestations
   4. Witness Gateways - Witness-only role with quorum enforcement
   5. Merkle-Rooted Execution Batches - Deterministic batching with proofs
   6. Transparency Logs - Append-only public Merkle logs
   7. Regulator-Operated Transparency Logs - Compliance enforcement

B. TIME MACHINE UI:
   Read-only, verification-first system for execution inspection

Phase II extends Phase I WITHOUT modifying its behavior.
All Phase I contracts remain unchanged and frozen.
"""

from intentusnet.phase2.gateway.enforcement import (
    GatewayEnforcer,
    GatewayIdentity,
    GatewayConfig,
    CanonicalExecutionEnvelope,
    GatewaySignature,
    AdmissionPolicy,
    AdmissionDecision,
)

from intentusnet.phase2.gateway.encryption import (
    SectionEncryptionConfig,
    EncryptedExecutionPayload,
    EncryptedSection,
    SectionType,
    DecryptionRequest,
    DecryptionResult,
    ExecutionDEK,
    KEKWrapper,
)

from intentusnet.phase2.federation.identity import (
    FederatedGatewayIdentity,
    GatewayDiscoveryDocument,
    FederationTrustPolicy,
)

from intentusnet.phase2.federation.verification import (
    CrossGatewayVerifier,
    MultiSignatureAttestation,
    ForeignExecutionRecord,
)

from intentusnet.phase2.witness.attestation import (
    WitnessGateway,
    WitnessAttestation,
    WitnessScope,
    WitnessQuorum,
    WitnessQuorumPolicy,
)

from intentusnet.phase2.merkle.batch import (
    ExecutionBatch,
    BatchLeaf,
    BatchRoot,
    BatchInclusionProof,
    BatchWitnessAttestation,
)

from intentusnet.phase2.transparency.log import (
    TransparencyLog,
    TransparencyCheckpoint,
    LogInclusionProof,
    ConsistencyProof,
)

from intentusnet.phase2.regulator.compliance import (
    RegulatorTransparencyLog,
    ComplianceProofPackage,
    JurisdictionPolicy,
    PublicationSLA,
)

from intentusnet.phase2.timemachine.api import (
    TimeMachineAPI,
    ExecutionQuery,
    ExecutionDetailResponse,
    ProofExportBundle,
)

__all__ = [
    # Gateway Enforcement
    "GatewayEnforcer",
    "GatewayIdentity",
    "GatewayConfig",
    "CanonicalExecutionEnvelope",
    "GatewaySignature",
    "AdmissionPolicy",
    "AdmissionDecision",
    # Section Encryption
    "SectionEncryptionConfig",
    "EncryptedExecutionPayload",
    "EncryptedSection",
    "SectionType",
    "DecryptionRequest",
    "DecryptionResult",
    "ExecutionDEK",
    "KEKWrapper",
    # Federation
    "FederatedGatewayIdentity",
    "GatewayDiscoveryDocument",
    "FederationTrustPolicy",
    "CrossGatewayVerifier",
    "MultiSignatureAttestation",
    "ForeignExecutionRecord",
    # Witness
    "WitnessGateway",
    "WitnessAttestation",
    "WitnessScope",
    "WitnessQuorum",
    "WitnessQuorumPolicy",
    # Merkle Batches
    "ExecutionBatch",
    "BatchLeaf",
    "BatchRoot",
    "BatchInclusionProof",
    "BatchWitnessAttestation",
    # Transparency
    "TransparencyLog",
    "TransparencyCheckpoint",
    "LogInclusionProof",
    "ConsistencyProof",
    # Regulator
    "RegulatorTransparencyLog",
    "ComplianceProofPackage",
    "JurisdictionPolicy",
    "PublicationSLA",
    # Time Machine
    "TimeMachineAPI",
    "ExecutionQuery",
    "ExecutionDetailResponse",
    "ProofExportBundle",
]

__version__ = "2.0.0"
