"""
Gateway Federation Identity (Phase II)

Provides gateway identity documents for federation discovery
and trust policy configuration.

Key concepts:
- Gateway identity documents at .well-known/intentusnet-gateway
- Public key distribution for cross-gateway verification
- Trust levels and policies for federated gateways
- Domain-based gateway discovery
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from intentusnet.phase2.gateway.enforcement import GatewayIdentity


# ===========================================================================
# Trust Levels
# ===========================================================================


class TrustLevel(Enum):
    """Trust levels for federated gateways."""
    UNTRUSTED = "untrusted"  # No trust, reject all
    VERIFIED = "verified"  # Identity verified but limited trust
    TRUSTED = "trusted"  # Full trust, accept executions
    AFFILIATE = "affiliate"  # Special relationship, extended trust


# ===========================================================================
# Gateway Discovery Document
# ===========================================================================


@dataclass
class GatewayEndpoint:
    """Endpoint configuration for a gateway."""
    url: str
    protocol: str = "https"
    version: str = "2.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "protocol": self.protocol,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GatewayEndpoint":
        return cls(
            url=data["url"],
            protocol=data.get("protocol", "https"),
            version=data.get("version", "2.0"),
        )


@dataclass
class GatewayCapabilities:
    """Capabilities advertised by a gateway."""
    supports_federation: bool = True
    supports_witness: bool = True
    supports_batching: bool = True
    supports_transparency: bool = True
    max_payload_size: int = 10 * 1024 * 1024  # 10 MB
    supported_encryption: List[str] = field(default_factory=lambda: ["AES-256-GCM"])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "supportsFederation": self.supports_federation,
            "supportsWitness": self.supports_witness,
            "supportsBatching": self.supports_batching,
            "supportsTransparency": self.supports_transparency,
            "maxPayloadSize": self.max_payload_size,
            "supportedEncryption": self.supported_encryption,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GatewayCapabilities":
        return cls(
            supports_federation=data.get("supportsFederation", True),
            supports_witness=data.get("supportsWitness", True),
            supports_batching=data.get("supportsBatching", True),
            supports_transparency=data.get("supportsTransparency", True),
            max_payload_size=data.get("maxPayloadSize", 10 * 1024 * 1024),
            supported_encryption=data.get("supportedEncryption", ["AES-256-GCM"]),
        )


@dataclass
class GatewayDiscoveryDocument:
    """
    Gateway discovery document for federation.

    Published at .well-known/intentusnet-gateway.json

    This document provides:
    - Gateway identity and public keys
    - Federation endpoints
    - Capability advertisement
    - Trust chain information

    Attributes:
        gateway_id: Unique identifier for the gateway
        domain: Domain name where this gateway is hosted
        identity: Gateway cryptographic identity
        endpoints: Available endpoints
        capabilities: Advertised capabilities
        federation_partners: Known federation partners
        created_at: Document creation time
        expires_at: Document expiration time
        signature: Gateway signature over the document
    """
    gateway_id: str
    domain: str
    identity: GatewayIdentity
    endpoints: Dict[str, GatewayEndpoint]
    capabilities: GatewayCapabilities
    federation_partners: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: Optional[str] = None
    signature: Optional[str] = None
    signature_key_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gatewayId": self.gateway_id,
            "domain": self.domain,
            "identity": self.identity.to_dict(),
            "endpoints": {k: v.to_dict() for k, v in self.endpoints.items()},
            "capabilities": self.capabilities.to_dict(),
            "federationPartners": self.federation_partners,
            "createdAt": self.created_at,
            "expiresAt": self.expires_at,
            "signature": self.signature,
            "signatureKeyId": self.signature_key_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GatewayDiscoveryDocument":
        return cls(
            gateway_id=data["gatewayId"],
            domain=data["domain"],
            identity=GatewayIdentity.from_dict(data["identity"]),
            endpoints={
                k: GatewayEndpoint.from_dict(v)
                for k, v in data.get("endpoints", {}).items()
            },
            capabilities=GatewayCapabilities.from_dict(data.get("capabilities", {})),
            federation_partners=data.get("federationPartners", []),
            created_at=data.get("createdAt", datetime.now(timezone.utc).isoformat()),
            expires_at=data.get("expiresAt"),
            signature=data.get("signature"),
            signature_key_id=data.get("signatureKeyId"),
        )

    def compute_content_hash(self) -> str:
        """Compute hash of document content (excluding signature)."""
        import json

        content = {
            "gatewayId": self.gateway_id,
            "domain": self.domain,
            "identity": self.identity.to_dict(),
            "endpoints": {k: v.to_dict() for k, v in self.endpoints.items()},
            "capabilities": self.capabilities.to_dict(),
            "federationPartners": self.federation_partners,
            "createdAt": self.created_at,
            "expiresAt": self.expires_at,
        }
        canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def is_expired(self) -> bool:
        """Check if the document has expired."""
        if self.expires_at is None:
            return False
        try:
            from dateutil.parser import isoparse

            expires = isoparse(self.expires_at)
            return datetime.now(timezone.utc) > expires
        except Exception:
            return True  # Treat parse errors as expired


# ===========================================================================
# Federated Gateway Identity
# ===========================================================================


@dataclass
class FederatedGatewayIdentity:
    """
    Identity information for a federated gateway.

    This is the local representation of a remote gateway's identity,
    including trust configuration and discovery information.

    Attributes:
        gateway_id: Remote gateway's identifier
        domain: Remote gateway's domain
        identity: Remote gateway's cryptographic identity
        trust_level: Local trust level for this gateway
        discovery_document: Cached discovery document
        last_verified: When identity was last verified
        verification_failures: Count of verification failures
    """
    gateway_id: str
    domain: str
    identity: GatewayIdentity
    trust_level: TrustLevel = TrustLevel.UNTRUSTED
    discovery_document: Optional[GatewayDiscoveryDocument] = None
    last_verified: Optional[str] = None
    verification_failures: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gatewayId": self.gateway_id,
            "domain": self.domain,
            "identity": self.identity.to_dict(),
            "trustLevel": self.trust_level.value,
            "discoveryDocument": (
                self.discovery_document.to_dict()
                if self.discovery_document else None
            ),
            "lastVerified": self.last_verified,
            "verificationFailures": self.verification_failures,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FederatedGatewayIdentity":
        doc_data = data.get("discoveryDocument")
        discovery_document = (
            GatewayDiscoveryDocument.from_dict(doc_data)
            if doc_data else None
        )

        return cls(
            gateway_id=data["gatewayId"],
            domain=data["domain"],
            identity=GatewayIdentity.from_dict(data["identity"]),
            trust_level=TrustLevel(data.get("trustLevel", "untrusted")),
            discovery_document=discovery_document,
            last_verified=data.get("lastVerified"),
            verification_failures=data.get("verificationFailures", 0),
        )

    def is_trusted(self) -> bool:
        """Check if this gateway is trusted for execution acceptance."""
        return self.trust_level in (TrustLevel.TRUSTED, TrustLevel.AFFILIATE)


# ===========================================================================
# Federation Trust Policy
# ===========================================================================


@dataclass
class TrustPolicyRule:
    """A rule in a federation trust policy."""
    domain_pattern: str  # e.g., "*.example.com" or "gateway.example.com"
    trust_level: TrustLevel
    require_signature_verification: bool = True
    require_discovery_document: bool = True
    max_verification_failures: int = 3

    def matches_domain(self, domain: str) -> bool:
        """Check if this rule matches a domain."""
        if self.domain_pattern == "*":
            return True
        if self.domain_pattern.startswith("*."):
            suffix = self.domain_pattern[2:]
            return domain.endswith(suffix) or domain == suffix[1:]
        return domain == self.domain_pattern


@dataclass
class FederationTrustPolicy:
    """
    Policy for trusting federated gateways.

    Attributes:
        policy_id: Unique identifier for this policy
        name: Human-readable policy name
        default_trust_level: Default trust for unknown gateways
        rules: List of trust rules (evaluated in order)
        require_discovery_document: Whether discovery doc is required
        max_discovery_age_seconds: Max age of cached discovery docs
        allowed_encryption_algorithms: Allowed encryption algorithms
    """
    policy_id: str
    name: str
    default_trust_level: TrustLevel = TrustLevel.UNTRUSTED
    rules: List[TrustPolicyRule] = field(default_factory=list)
    require_discovery_document: bool = True
    max_discovery_age_seconds: int = 86400  # 24 hours
    allowed_encryption_algorithms: Set[str] = field(
        default_factory=lambda: {"AES-256-GCM"}
    )

    def evaluate(self, domain: str) -> TrustLevel:
        """Evaluate trust level for a domain."""
        for rule in self.rules:
            if rule.matches_domain(domain):
                return rule.trust_level
        return self.default_trust_level

    def get_rule(self, domain: str) -> Optional[TrustPolicyRule]:
        """Get the matching rule for a domain."""
        for rule in self.rules:
            if rule.matches_domain(domain):
                return rule
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policyId": self.policy_id,
            "name": self.name,
            "defaultTrustLevel": self.default_trust_level.value,
            "rules": [
                {
                    "domainPattern": r.domain_pattern,
                    "trustLevel": r.trust_level.value,
                    "requireSignatureVerification": r.require_signature_verification,
                    "requireDiscoveryDocument": r.require_discovery_document,
                    "maxVerificationFailures": r.max_verification_failures,
                }
                for r in self.rules
            ],
            "requireDiscoveryDocument": self.require_discovery_document,
            "maxDiscoveryAgeSeconds": self.max_discovery_age_seconds,
            "allowedEncryptionAlgorithms": list(self.allowed_encryption_algorithms),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FederationTrustPolicy":
        rules = [
            TrustPolicyRule(
                domain_pattern=r["domainPattern"],
                trust_level=TrustLevel(r["trustLevel"]),
                require_signature_verification=r.get(
                    "requireSignatureVerification", True
                ),
                require_discovery_document=r.get("requireDiscoveryDocument", True),
                max_verification_failures=r.get("maxVerificationFailures", 3),
            )
            for r in data.get("rules", [])
        ]

        return cls(
            policy_id=data["policyId"],
            name=data["name"],
            default_trust_level=TrustLevel(data.get("defaultTrustLevel", "untrusted")),
            rules=rules,
            require_discovery_document=data.get("requireDiscoveryDocument", True),
            max_discovery_age_seconds=data.get("maxDiscoveryAgeSeconds", 86400),
            allowed_encryption_algorithms=set(
                data.get("allowedEncryptionAlgorithms", ["AES-256-GCM"])
            ),
        )


# ===========================================================================
# Gateway Discovery Service
# ===========================================================================


class GatewayDiscoveryService:
    """
    Service for discovering and caching federated gateway identities.

    In production, this would fetch discovery documents over HTTPS.
    """

    def __init__(self, trust_policy: FederationTrustPolicy):
        self._policy = trust_policy
        self._cache: Dict[str, FederatedGatewayIdentity] = {}

    @property
    def policy(self) -> FederationTrustPolicy:
        return self._policy

    def register_gateway(
        self,
        document: GatewayDiscoveryDocument,
        verify_signature: bool = True,
    ) -> FederatedGatewayIdentity:
        """
        Register a gateway from its discovery document.

        Args:
            document: The gateway's discovery document
            verify_signature: Whether to verify the document signature

        Returns:
            FederatedGatewayIdentity for the gateway
        """
        # Evaluate trust level
        trust_level = self._policy.evaluate(document.domain)

        # Check document expiration
        if document.is_expired():
            trust_level = TrustLevel.UNTRUSTED

        identity = FederatedGatewayIdentity(
            gateway_id=document.gateway_id,
            domain=document.domain,
            identity=document.identity,
            trust_level=trust_level,
            discovery_document=document,
            last_verified=datetime.now(timezone.utc).isoformat(),
            verification_failures=0,
        )

        self._cache[document.gateway_id] = identity
        return identity

    def get_gateway(self, gateway_id: str) -> Optional[FederatedGatewayIdentity]:
        """Get a cached gateway identity."""
        return self._cache.get(gateway_id)

    def get_gateway_by_domain(self, domain: str) -> Optional[FederatedGatewayIdentity]:
        """Get a gateway by domain."""
        for identity in self._cache.values():
            if identity.domain == domain:
                return identity
        return None

    def list_gateways(
        self,
        trust_level: Optional[TrustLevel] = None,
    ) -> List[FederatedGatewayIdentity]:
        """List all cached gateways, optionally filtered by trust level."""
        gateways = list(self._cache.values())
        if trust_level is not None:
            gateways = [g for g in gateways if g.trust_level == trust_level]
        return gateways

    def remove_gateway(self, gateway_id: str) -> bool:
        """Remove a gateway from the cache."""
        if gateway_id in self._cache:
            del self._cache[gateway_id]
            return True
        return False

    def record_verification_failure(self, gateway_id: str) -> None:
        """Record a verification failure for a gateway."""
        if gateway_id in self._cache:
            identity = self._cache[gateway_id]
            identity.verification_failures += 1

            # Demote trust if failures exceed threshold
            rule = self._policy.get_rule(identity.domain)
            max_failures = rule.max_verification_failures if rule else 3

            if identity.verification_failures >= max_failures:
                identity.trust_level = TrustLevel.UNTRUSTED
