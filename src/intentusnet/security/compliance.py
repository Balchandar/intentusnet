"""
Compliance Mode Configuration (Phase I)

This module defines compliance mode settings that enforce security
requirements for regulated workloads (HIPAA, SOC 2, PCI-DSS).

Compliance Mode Requirements:
- Signed WAL entries (mandatory for audit trail integrity)
- Minimum cryptographic parameters (256-bit hashes, 256-bit keys)
- Determinism enforcement (require_determinism=True)
- PII redaction policy (must be configured)

See: docs/phase-i-remediation-plan.md Section 6
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import hashlib


class ComplianceLevel(Enum):
    """
    Compliance levels for IntentusNet deployments.

    DEVELOPMENT: No restrictions, for local testing only
    STANDARD: Recommended defaults, suitable for production
    REGULATED: Strict requirements for HIPAA/SOC2/PCI-DSS workloads
    """
    DEVELOPMENT = "development"
    STANDARD = "standard"
    REGULATED = "regulated"


class ComplianceError(RuntimeError):
    """Raised when compliance requirements are not met."""
    pass


@dataclass
class ComplianceConfig:
    """
    Compliance configuration for IntentusNet.

    Attributes:
        level: The compliance level (DEVELOPMENT, STANDARD, REGULATED)
        require_signed_wal: Whether WAL entries must be signed
        require_determinism: Whether deterministic routing is required
        require_pii_policy: Whether PII redaction policy must be configured
        min_hash_bits: Minimum hash output size in bits
        min_key_bits: Minimum encryption key size in bits
        audit_all_access: Whether all data access must be logged
    """
    level: ComplianceLevel = ComplianceLevel.STANDARD

    # Security requirements (defaults for STANDARD)
    require_signed_wal: bool = False
    require_determinism: bool = True
    require_pii_policy: bool = False
    min_hash_bits: int = 256
    min_key_bits: int = 256
    audit_all_access: bool = False

    @classmethod
    def for_level(cls, level: ComplianceLevel) -> "ComplianceConfig":
        """
        Create compliance config for a specific level.

        DEVELOPMENT: All restrictions disabled (NOT for production)
        STANDARD: Recommended defaults
        REGULATED: Strict requirements for compliance
        """
        if level == ComplianceLevel.DEVELOPMENT:
            return cls(
                level=level,
                require_signed_wal=False,
                require_determinism=False,  # Allow PARALLEL for testing
                require_pii_policy=False,
                min_hash_bits=256,
                min_key_bits=256,
                audit_all_access=False,
            )
        elif level == ComplianceLevel.STANDARD:
            return cls(
                level=level,
                require_signed_wal=False,
                require_determinism=True,
                require_pii_policy=False,
                min_hash_bits=256,
                min_key_bits=256,
                audit_all_access=False,
            )
        elif level == ComplianceLevel.REGULATED:
            return cls(
                level=level,
                require_signed_wal=True,   # MANDATORY for audit trail
                require_determinism=True,   # MANDATORY for reproducibility
                require_pii_policy=True,    # MANDATORY for data protection
                min_hash_bits=256,          # SHA-256 minimum
                min_key_bits=256,           # AES-256 minimum
                audit_all_access=True,      # MANDATORY for audit
            )
        else:
            raise ValueError(f"Unknown compliance level: {level}")

    def validate(self) -> None:
        """
        Validate that compliance requirements are internally consistent.

        Raises:
            ComplianceError: If configuration is invalid
        """
        if self.min_hash_bits < 256:
            raise ComplianceError(
                f"min_hash_bits must be >= 256, got {self.min_hash_bits}. "
                "Hashes shorter than 256 bits are vulnerable to collision attacks."
            )

        if self.min_key_bits < 256:
            raise ComplianceError(
                f"min_key_bits must be >= 256, got {self.min_key_bits}. "
                "Keys shorter than 256 bits do not meet compliance requirements."
            )

        if self.level == ComplianceLevel.REGULATED:
            if not self.require_signed_wal:
                raise ComplianceError(
                    "REGULATED compliance level requires require_signed_wal=True. "
                    "Unsigned WAL entries cannot provide audit trail integrity."
                )
            if not self.require_determinism:
                raise ComplianceError(
                    "REGULATED compliance level requires require_determinism=True. "
                    "Non-deterministic routing prevents reproducible audits."
                )
            if not self.require_pii_policy:
                raise ComplianceError(
                    "REGULATED compliance level requires require_pii_policy=True. "
                    "PII protection is mandatory for HIPAA/SOC2/PCI-DSS."
                )


class ComplianceValidator:
    """
    Runtime validator for compliance requirements.

    Use this to check that components meet compliance requirements
    before execution.
    """

    def __init__(self, config: ComplianceConfig):
        self._config = config
        config.validate()  # Ensure config is valid

    @property
    def config(self) -> ComplianceConfig:
        return self._config

    def validate_hash_algorithm(self, algorithm: str, output_bits: int) -> None:
        """
        Validate that a hash algorithm meets minimum requirements.

        Args:
            algorithm: Name of the algorithm (e.g., "sha256")
            output_bits: Output size in bits

        Raises:
            ComplianceError: If algorithm doesn't meet requirements
        """
        if output_bits < self._config.min_hash_bits:
            raise ComplianceError(
                f"Hash algorithm '{algorithm}' produces {output_bits} bits, "
                f"but compliance requires >= {self._config.min_hash_bits} bits. "
                f"Use SHA-256 or stronger."
            )

    def validate_key_size(self, algorithm: str, key_bits: int) -> None:
        """
        Validate that an encryption key meets minimum requirements.

        Args:
            algorithm: Name of the algorithm (e.g., "aes-256-gcm")
            key_bits: Key size in bits

        Raises:
            ComplianceError: If key size doesn't meet requirements
        """
        if key_bits < self._config.min_key_bits:
            raise ComplianceError(
                f"Encryption algorithm '{algorithm}' uses {key_bits}-bit key, "
                f"but compliance requires >= {self._config.min_key_bits} bits. "
                f"Use AES-256 or stronger."
            )

    def validate_router_config(self, require_determinism: bool) -> None:
        """
        Validate that router configuration meets compliance requirements.

        Args:
            require_determinism: The router's require_determinism setting

        Raises:
            ComplianceError: If router config doesn't meet requirements
        """
        if self._config.require_determinism and not require_determinism:
            raise ComplianceError(
                "Compliance mode requires deterministic routing, "
                "but router has require_determinism=False. "
                "This allows PARALLEL strategy which is non-deterministic."
            )

    def validate_wal_signing(self, signing_enabled: bool) -> None:
        """
        Validate that WAL signing meets compliance requirements.

        Args:
            signing_enabled: Whether WAL signing is enabled

        Raises:
            ComplianceError: If WAL signing requirements not met
        """
        if self._config.require_signed_wal and not signing_enabled:
            raise ComplianceError(
                "Compliance mode requires signed WAL entries for audit trail integrity. "
                "Enable WAL signing or use a lower compliance level."
            )

    def validate_pii_policy(self, policy_configured: bool) -> None:
        """
        Validate that PII policy meets compliance requirements.

        Args:
            policy_configured: Whether a PII policy is configured

        Raises:
            ComplianceError: If PII policy requirements not met
        """
        if self._config.require_pii_policy and not policy_configured:
            raise ComplianceError(
                "Compliance mode requires PII redaction policy to be configured. "
                "Configure a PII policy or use a lower compliance level."
            )


# ===========================================================================
# Cryptographic Parameter Validation
# ===========================================================================

APPROVED_HASH_ALGORITHMS = {
    "sha256": 256,
    "sha384": 384,
    "sha512": 512,
    "sha3-256": 256,
    "sha3-384": 384,
    "sha3-512": 512,
    "blake2b": 512,
    "blake2s": 256,
}

APPROVED_ENCRYPTION_ALGORITHMS = {
    "aes-256-gcm": 256,
    "aes-256-cbc": 256,
    "chacha20-poly1305": 256,
}


def validate_hash_truncation(
    full_hash: str,
    truncated_length: int,
    compliance: ComplianceConfig
) -> None:
    """
    Validate that hash truncation meets compliance requirements.

    Phase I remediation: Hash truncation below 256 bits is PROHIBITED
    because it enables birthday attacks on low-entropy inputs.

    Args:
        full_hash: The full hash value (hex string)
        truncated_length: Requested truncation length in characters
        compliance: The compliance configuration

    Raises:
        ComplianceError: If truncation would violate requirements
    """
    # Each hex character = 4 bits
    truncated_bits = truncated_length * 4
    min_bits = compliance.min_hash_bits

    if truncated_bits < min_bits:
        raise ComplianceError(
            f"Hash truncation to {truncated_length} characters ({truncated_bits} bits) "
            f"is below the minimum of {min_bits} bits. "
            f"Truncated hashes are vulnerable to collision attacks. "
            f"Use full hash output or HMAC for correlation without reversal."
        )


def get_sha256_full(data: bytes) -> str:
    """
    Compute full SHA-256 hash (no truncation).

    This is the ONLY approved hash function for Phase I compliance.
    Truncation is PROHIBITED.

    Returns:
        64-character hex string (256 bits)
    """
    return hashlib.sha256(data).hexdigest()


# ===========================================================================
# Global Compliance State
# ===========================================================================

_global_compliance: Optional[ComplianceConfig] = None


def set_global_compliance(config: ComplianceConfig) -> None:
    """
    Set the global compliance configuration.

    This should be called once at application startup.
    """
    global _global_compliance
    config.validate()
    _global_compliance = config


def get_global_compliance() -> ComplianceConfig:
    """
    Get the global compliance configuration.

    Returns STANDARD if not explicitly set.
    """
    global _global_compliance
    if _global_compliance is None:
        _global_compliance = ComplianceConfig.for_level(ComplianceLevel.STANDARD)
    return _global_compliance


def require_compliance(level: ComplianceLevel) -> ComplianceValidator:
    """
    Get a compliance validator, ensuring the global config meets the level.

    Args:
        level: The minimum required compliance level

    Returns:
        ComplianceValidator for the current global config

    Raises:
        ComplianceError: If global config doesn't meet the level
    """
    config = get_global_compliance()

    level_order = {
        ComplianceLevel.DEVELOPMENT: 0,
        ComplianceLevel.STANDARD: 1,
        ComplianceLevel.REGULATED: 2,
    }

    if level_order[config.level] < level_order[level]:
        raise ComplianceError(
            f"Operation requires compliance level {level.value}, "
            f"but global config is {config.level.value}. "
            f"Use set_global_compliance() to upgrade."
        )

    return ComplianceValidator(config)
