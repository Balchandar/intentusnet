"""
WAL Signing Implementation (Phase I REGULATED)

This module provides Ed25519 signing for WAL entries.

REQUIREMENTS:
- Signatures use Ed25519 (256-bit security level)
- Key IDs are SHA256 hashes of public keys (first 16 chars)
- Verification is offline-capable (no network required)

KEY MANAGEMENT ASSUMPTIONS:
- Private keys are provided at initialization (from HSM, KMS, or secure file)
- Public keys can be loaded from file or embedded in verifier
- Key rotation is handled by changing key_id in WALWriter

This is the MINIMUM viable signing for Phase I REGULATED.
Production deployments SHOULD use HSM-backed keys.
"""

from __future__ import annotations

import hashlib
from typing import Dict, Optional

# cryptography is already a dependency (used by EMCL)
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature


class Ed25519WALSigner:
    """
    Ed25519 signer for WAL entries.

    Implements WALSigner protocol.

    Usage:
        # From raw key bytes (32 bytes)
        signer = Ed25519WALSigner.from_private_bytes(key_bytes)

        # From PEM file
        signer = Ed25519WALSigner.from_pem_file("/path/to/key.pem")

        # Generate new key (for testing only)
        signer = Ed25519WALSigner.generate()
    """

    def __init__(self, private_key: Ed25519PrivateKey):
        self._private_key = private_key
        self._public_key = private_key.public_key()

        # Key ID is SHA256 of public key bytes (first 16 chars for readability)
        public_bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        self._key_id = hashlib.sha256(public_bytes).hexdigest()[:16]

    @property
    def key_id(self) -> str:
        """Unique identifier for this signing key."""
        return self._key_id

    @property
    def public_key_bytes(self) -> bytes:
        """Raw public key bytes (for verification)."""
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )

    def sign(self, data: bytes) -> bytes:
        """Sign data using Ed25519. Returns 64-byte signature."""
        return self._private_key.sign(data)

    @classmethod
    def generate(cls) -> "Ed25519WALSigner":
        """
        Generate a new Ed25519 key pair.

        WARNING: Use only for testing. Production keys should come from
        HSM, KMS, or secure key generation ceremony.
        """
        private_key = Ed25519PrivateKey.generate()
        return cls(private_key)

    @classmethod
    def from_private_bytes(cls, key_bytes: bytes) -> "Ed25519WALSigner":
        """Create signer from raw 32-byte private key."""
        private_key = Ed25519PrivateKey.from_private_bytes(key_bytes)
        return cls(private_key)

    @classmethod
    def from_pem_file(cls, path: str, password: Optional[bytes] = None) -> "Ed25519WALSigner":
        """Load signer from PEM-encoded private key file."""
        with open(path, "rb") as f:
            private_key = serialization.load_pem_private_key(
                f.read(),
                password=password,
            )
        if not isinstance(private_key, Ed25519PrivateKey):
            raise TypeError(f"Expected Ed25519 private key, got {type(private_key)}")
        return cls(private_key)

    def export_public_pem(self) -> bytes:
        """Export public key as PEM for distribution to verifiers."""
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )


class Ed25519WALVerifier:
    """
    Ed25519 verifier for WAL entries.

    Implements WALVerifier protocol.

    Verification is OFFLINE - all public keys must be pre-loaded.

    Usage:
        verifier = Ed25519WALVerifier()
        verifier.add_public_key(key_id, public_key_bytes)

        if entry.verify_signature(verifier):
            print("Valid")
    """

    def __init__(self):
        self._public_keys: Dict[str, Ed25519PublicKey] = {}

    def add_public_key(self, key_id: str, public_key_bytes: bytes) -> None:
        """
        Add a public key for verification.

        Args:
            key_id: The key identifier (must match signer's key_id)
            public_key_bytes: Raw 32-byte Ed25519 public key
        """
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        self._public_keys[key_id] = public_key

    def add_public_key_pem(self, key_id: str, pem_data: bytes) -> None:
        """Add a public key from PEM format."""
        public_key = serialization.load_pem_public_key(pem_data)
        if not isinstance(public_key, Ed25519PublicKey):
            raise TypeError(f"Expected Ed25519 public key, got {type(public_key)}")
        self._public_keys[key_id] = public_key

    def add_from_signer(self, signer: Ed25519WALSigner) -> None:
        """
        Add public key from a signer.
        Convenience method for testing.
        """
        self.add_public_key(signer.key_id, signer.public_key_bytes)

    def get_public_key(self, key_id: str) -> Optional[bytes]:
        """Get public key bytes for key_id, or None if not found."""
        if key_id not in self._public_keys:
            return None
        return self._public_keys[key_id].public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )

    def verify(self, data: bytes, signature: bytes, key_id: str) -> bool:
        """
        Verify signature.

        Args:
            data: Original data that was signed
            signature: 64-byte Ed25519 signature
            key_id: Key identifier to use for verification

        Returns:
            True if valid, False if invalid or key not found
        """
        if key_id not in self._public_keys:
            return False

        public_key = self._public_keys[key_id]

        try:
            public_key.verify(signature, data)
            return True
        except InvalidSignature:
            return False

    def has_key(self, key_id: str) -> bool:
        """Check if a key is registered."""
        return key_id in self._public_keys

    @property
    def key_ids(self) -> list[str]:
        """List all registered key IDs."""
        return list(self._public_keys.keys())
