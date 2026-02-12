"""
Gateway Federation Module (Phase II)

Enables cross-gateway execution verification and multi-signature attestations.

Key concepts:
- Gateway identity documents (.well-known)
- Cross-gateway execution verification
- Multi-signature execution attestations
- Foreign execution storage (non-authoritative)
- Cross-domain replay with lineage preservation
"""

from intentusnet.phase2.federation.identity import (
    FederatedGatewayIdentity,
    GatewayDiscoveryDocument,
    FederationTrustPolicy,
    TrustLevel,
)

from intentusnet.phase2.federation.verification import (
    CrossGatewayVerifier,
    MultiSignatureAttestation,
    ForeignExecutionRecord,
    FederatedVerificationResult,
)

__all__ = [
    "FederatedGatewayIdentity",
    "GatewayDiscoveryDocument",
    "FederationTrustPolicy",
    "TrustLevel",
    "CrossGatewayVerifier",
    "MultiSignatureAttestation",
    "ForeignExecutionRecord",
    "FederatedVerificationResult",
]
