"""
Gateway Enforcement Module (Phase II)

The gateway is the root of trust in IntentusNet Phase II.
It is responsible for:
- Canonical execution construction
- Mandatory gateway signing
- Mandatory encryption enforcement
- Policy-based admission control
- Replay enforcement with parentExecutionHash

CRITICAL: Agents MUST NOT generate final execution records.
Only the gateway constructs canonical execution envelopes.
"""

from intentusnet.phase2.gateway.enforcement import (
    GatewayEnforcer,
    GatewayIdentity,
    GatewayConfig,
    CanonicalExecutionEnvelope,
    GatewaySignature,
    AdmissionPolicy,
    AdmissionDecision,
    AdmissionDeniedError,
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
    SectionEncryptor,
)

__all__ = [
    # Enforcement
    "GatewayEnforcer",
    "GatewayIdentity",
    "GatewayConfig",
    "CanonicalExecutionEnvelope",
    "GatewaySignature",
    "AdmissionPolicy",
    "AdmissionDecision",
    "AdmissionDeniedError",
    # Encryption
    "SectionEncryptionConfig",
    "EncryptedExecutionPayload",
    "EncryptedSection",
    "SectionType",
    "DecryptionRequest",
    "DecryptionResult",
    "ExecutionDEK",
    "KEKWrapper",
    "SectionEncryptor",
]
