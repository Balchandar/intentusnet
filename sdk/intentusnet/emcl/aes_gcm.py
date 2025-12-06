"""
AES-GCM EMCL Provider
---------------------

Production-ready AES-256-GCM encryption & decryption for EMCL envelopes.

Features:
- 256-bit key
- 96-bit nonce (recommended for GCM)
- Authenticated encryption (GCM tag)
- Identity chain support
- JSON-safe ciphertext (base64)

This is the secure alternative to simple_hmac.py.
"""

from __future__ import annotations
import base64
import os
import json
from typing import Dict, Any, List

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..protocol.models import EMCLEnvelope
from ..protocol.errors import EMCLValidationError
from ..utils.json import json_dumps, json_loads
from .identity_chain import extend_identity_chain


class AESGCMEMCLProvider:
    """
    AES-256-GCM implementation for EMCL encryption/decryption.

    Parameters:
        key: bytes or hex string (must be 32 bytes)
        emcl_version: EMCL spec version string
        identity: Optional agent identity (added to identity chain)
    """

    def __init__(
        self,
        key: bytes | str,
        emcl_version: str = "1.0",
        identity: str | None = None
    ) -> None:
        if isinstance(key, str):
            key = bytes.fromhex(key)

        if len(key) != 32:
            raise ValueError("AES-GCM key must be exactly 32 bytes (256-bit).")

        self._key = key
        self._aesgcm = AESGCM(key)
        self._emcl_version = emcl_version
        self._identity = identity

    # Encrypt

    def encrypt(self, body: Dict[str, Any], identity_chain: List[str] | None = None) -> EMCLEnvelope:
        """
        Encrypt the given payload and return an EMCLEnvelope.
        """
        plaintext = json_dumps(body).encode("utf-8")

        # GCM standard: 96-bit nonce
        nonce = os.urandom(12)

        # Additional authenticated data (logical)
        aad = b"emcl-aes-gcm"

        ciphertext = self._aesgcm.encrypt(nonce, plaintext, aad)

        # Extend identity chain
        new_chain = extend_identity_chain(identity_chain or [], self._identity)

        return EMCLEnvelope(
            emclVersion=self._emcl_version,
            ciphertext=base64.b64encode(ciphertext).decode("utf-8"),
            nonce=base64.b64encode(nonce).decode("utf-8"),
            hmac="",  # Not used in AES-GCM (authentication built into tag)
            identityChain=new_chain,
        )

    # Decrypt

    def decrypt(self, envelope: EMCLEnvelope) -> Dict[str, Any]:
        """
        Validate integrity and decrypt payload.

        Raises:
            EMCLValidationError on bad ciphertext/tag.
        """
        try:
            nonce = base64.b64decode(envelope.nonce)
            ciphertext = base64.b64decode(envelope.ciphertext)
        except Exception:
            raise EMCLValidationError("Invalid base64 values in EMCL envelope.")

        aad = b"emcl-aes-gcm"

        try:
            plaintext = self._aesgcm.decrypt(nonce, ciphertext, aad)
        except Exception as e:
            raise EMCLValidationError(f"EMCL AES-GCM decryption failed: {e}")

        # Decode JSON body
        try:
            return json_loads(plaintext.decode("utf-8"))
        except Exception:
            raise EMCLValidationError("EMCL decrypted plaintext is invalid JSON.")
