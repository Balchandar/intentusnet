from __future__ import annotations
import json
import hmac
import hashlib
from typing import Dict, Any

from intentusnet.protocol.models import EMCLEnvelope
from intentusnet.protocol.errors import EMCLValidationError


class SimpleHMACEMCLProvider:
    """
    Lightweight EMCL provider for integrity-only mode.
    No encryption — plaintext is signed using HMAC-SHA256.

    Suitable for:
    - Local development
    - Debugging
    - Non-sensitive payloads
    """

    def __init__(self, key: str, emcl_version: str = "1.0"):
        self._key = key.encode("utf-8")
        self._emcl_version = emcl_version

    def encrypt(self, body: Dict[str, Any]) -> EMCLEnvelope:
        plaintext = json.dumps(body, sort_keys=True, separators=(",", ":"))
        nonce = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()[:32]

        signature = hmac.new(
            self._key,
            (nonce + plaintext).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return EMCLEnvelope(
            emclVersion=self._emcl_version,
            ciphertext=plaintext,
            nonce=nonce,
            hmac=signature,
            identityChain=[],
        )

    def decrypt(self, envelope: EMCLEnvelope) -> Dict[str, Any]:
        expected = hmac.new(
            self._key,
            (envelope.nonce + envelope.ciphertext).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected, envelope.hmac):
            raise EMCLValidationError("HMAC signature mismatch")

        return json.loads(envelope.ciphertext)
