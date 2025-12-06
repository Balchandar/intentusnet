from __future__ import annotations
import json
import hmac
import hashlib
from typing import Dict, Any
from ..protocol.models import EMCLEnvelope
from ..protocol.errors import EMCLValidationError


class SimpleHMACEMCLProvider:
    """
    Demo EMCL provider:
    - Signs JSON body with HMAC-SHA256
    - Ciphertext is just the plaintext JSON (no real encryption).
    Replace with AES-GCM in production.
    """

    def __init__(self, key: str, emcl_version: str = "1.0") -> None:
        self._key = key.encode("utf-8")
        self._emcl_version = emcl_version

    def encrypt(self, body: Dict[str, Any]) -> EMCLEnvelope:
        nonce = hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()[:32]
        plaintext = json.dumps(body, separators=(",", ":"), sort_keys=True)
        ciphertext = plaintext
        sig = hmac.new(self._key, (nonce + ciphertext).encode("utf-8"), hashlib.sha256).hexdigest()
        return EMCLEnvelope(
            emclVersion=self._emcl_version,
            ciphertext=ciphertext,
            nonce=nonce,
            hmac=sig,
            identityChain=[],
        )

    def decrypt(self, envelope: EMCLEnvelope) -> Dict[str, Any]:
        expected = hmac.new(
            self._key,
            (envelope.nonce + envelope.ciphertext).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, envelope.hmac):
            raise EMCLValidationError("EMCL HMAC validation failed")
        return json.loads(envelope.ciphertext)
