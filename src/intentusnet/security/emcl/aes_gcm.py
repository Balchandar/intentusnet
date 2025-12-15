from __future__ import annotations

import os
import base64
import json
from typing import Dict, Any, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore

from intentusnet.protocol.emcl import EMCLEnvelope
from intentusnet.protocol.errors import EMCLValidationError
from .base import EMCLProvider


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _json_loads(s: str) -> Any:
    return json.loads(s)


class AESGCMEMCLProvider(EMCLProvider):
    """
    AES-256-GCM EMCL provider.

    - 256-bit key (32 bytes)
    - 96-bit nonce (12 bytes)
    - Authenticated encryption (GCM tag included)
    - Base64 encoding for JSON-safe transport
    """

    def __init__(self, key: str) -> None:
        if not key:
            raise EMCLValidationError("EMCL AES-GCM key must not be empty")

        # Normalize key to 32 bytes using SHA-256 or direct bytes if already 32
        raw = key.encode("utf-8")
        if len(raw) == 32:
            self._key = raw
        else:
            import hashlib

            self._key = hashlib.sha256(raw).digest()

        self._aesgcm = AESGCM(self._key)

    # ------------------------------------------------------------------
    # EMCLProvider implementation
    # ------------------------------------------------------------------
    def encrypt(self, body: Dict[str, Any]) -> EMCLEnvelope:
        try:
            plaintext = _json_dumps(body).encode("utf-8")
        except Exception as e:
            raise EMCLValidationError(f"EMCL AES-GCM: cannot encode body to JSON: {e}")

        # 96-bit nonce for GCM
        nonce = os.urandom(12)
        aad = b"emcl-aes-gcm"

        try:
            ct = self._aesgcm.encrypt(nonce, plaintext, aad)
        except Exception as e:
            raise EMCLValidationError(f"EMCL AES-GCM encryption failed: {e}")

        # AESGCM returns ciphertext||tag in ct
        nonce_b64 = base64.b64encode(nonce).decode("ascii")
        ct_b64 = base64.b64encode(ct).decode("ascii")

        # For simplicity we treat entire ct as cipherText, no separate tag field
        return EMCLEnvelope(
            cipherText=ct_b64,
            iv=nonce_b64,
            tag="",  # reserved, not needed when using AESGCM's combined output
            identityChain=[],
        )

    def decrypt(self, envelope: EMCLEnvelope) -> Dict[str, Any]:
        try:
            nonce = base64.b64decode(envelope.iv)
            ciphertext = base64.b64decode(envelope.cipherText)
        except Exception:
            raise EMCLValidationError("EMCL AES-GCM: invalid base64 values in envelope")

        aad = b"emcl-aes-gcm"

        try:
            plaintext = self._aesgcm.decrypt(nonce, ciphertext, aad)
        except Exception as e:
            raise EMCLValidationError(f"EMCL AES-GCM decryption failed: {e}")

        try:
            return _json_loads(plaintext.decode("utf-8"))
        except Exception:
            raise EMCLValidationError("EMCL AES-GCM: decrypted plaintext is invalid JSON")
