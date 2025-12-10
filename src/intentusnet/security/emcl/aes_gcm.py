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
"""

from __future__ import annotations
import base64
import os
from typing import Dict, Any, List

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from intentusnet.protocol.models import EMCLEnvelope
from intentusnet.protocol.errors import EMCLValidationError
from intentusnet.utils.json import json_dumps, json_loads
from .identity_chain import extend_identity_chain


class AESGCMEMCLProvider:
    """
    AES-256-GCM encrypted EMCL provider.
    Provides:
    - Confidentiality
    - Integrity
    - Authenticated identity chain
    """

    def __init__(
        self,
        key: bytes | str,
        emcl_version: str = "1.0",
        identity: str | None = None,
    ):
        if isinstance(key, str):
            key = bytes.fromhex(key)  # expect 32-byte hex string

        if len(key) != 32:
            raise ValueError("AES-GCM key must be exactly 32 bytes")

        self._key = key
        self._aesgcm = AESGCM(key)
        self._emcl_version = emcl_version
        self._identity = identity

    # --- Key Helpers -------------------------------------------------

    @staticmethod
    def generate_key() -> bytes:
        return os.urandom(32)

    @staticmethod
    def generate_key_hex() -> str:
        return AESGCMEMCLProvider.generate_key().hex()

    # --- Encrypt -----------------------------------------------------

    def encrypt(self, body: Dict[str, Any], identity_chain: List[str] | None = None) -> EMCLEnvelope:
        plaintext = json_dumps(body).encode("utf-8")

        nonce = os.urandom(12)  # GCM standard: 96-bit nonce
        aad = b"intentusnet-emcl-aes-gcm"

        ciphertext = self._aesgcm.encrypt(nonce, plaintext, aad)

        new_chain = extend_identity_chain(identity_chain or [], self._identity)

        return EMCLEnvelope(
            emclVersion=self._emcl_version,
            ciphertext=base64.b64encode(ciphertext).decode("utf-8"),
            nonce=base64.b64encode(nonce).decode("utf-8"),
            hmac="",  # GCM includes integrity tag internally
            identityChain=new_chain,
        )

    # --- Decrypt -----------------------------------------------------

    def decrypt(self, envelope: EMCLEnvelope) -> Dict[str, Any]:
        try:
            nonce = base64.b64decode(envelope.nonce)
            ciphertext = base64.b64decode(envelope.ciphertext)
        except Exception:
            raise EMCLValidationError("Invalid base64 in EMCL envelope")

        aad = b"intentusnet-emcl-aes-gcm"

        try:
            plaintext = self._aesgcm.decrypt(nonce, ciphertext, aad)
        except Exception as e:
            raise EMCLValidationError(f"AES-GCM decryption failed: {e}")

        try:
            return json_loads(plaintext.decode("utf-8"))
        except Exception:
            raise EMCLValidationError("Decrypted EMCL payload is invalid JSON")
