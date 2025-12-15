from __future__ import annotations

import json
import hmac
import hashlib
from typing import Dict, Any

from intentusnet.protocol.emcl import EMCLEnvelope
from intentusnet.protocol.errors import EMCLValidationError
from .base import EMCLProvider


class SimpleHMACEMCLProvider(EMCLProvider):
    """
    Demo EMCL provider:

    - Ciphertext is the plaintext JSON (no encryption).
    - HMAC-SHA256 over nonce + ciphertext for integrity.

    DO NOT use this in production when confidentiality is required.
    """

    def __init__(self, key: str) -> None:
        if not key:
            raise EMCLValidationError("EMCL HMAC key must not be empty")
        self._key = key.encode("utf-8")

    def encrypt(self, body: Dict[str, Any]) -> EMCLEnvelope:
        nonce = hashlib.sha256(str(body).encode("utf-8")).hexdigest()[:16]

        ciphertext = json.dumps(body, separators=(",", ":"), ensure_ascii=False)

        sig = hmac.new(
            self._key,
            (nonce + ciphertext).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # We reuse EMCLEnvelope structure:
        # - cipherText: JSON string
        # - iv: nonce
        # - tag: HMAC signature
        return EMCLEnvelope(
            cipherText=ciphertext,
            iv=nonce,
            tag=sig,
            identityChain=[],
        )

    def decrypt(self, envelope: EMCLEnvelope) -> Dict[str, Any]:
        expected = hmac.new(
            self._key,
            (envelope.iv + envelope.cipherText).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected, envelope.tag):
            raise EMCLValidationError("EMCL HMAC validation failed")

        try:
            return json.loads(envelope.cipherText)
        except Exception as e:
            raise EMCLValidationError(f"EMCL HMAC: invalid ciphertext JSON: {e}")
