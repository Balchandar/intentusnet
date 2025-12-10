from __future__ import annotations
from typing import Protocol, Dict, Any, Optional
import os

from intentusnet.protocol.models import EMCLEnvelope
from .aes_gcm import AESGCMEMCLProvider
from .simple_hmac import SimpleHMACEMCLProvider


class EMCLProvider(Protocol):
    """Base protocol for EMCL encrypt/decrypt providers."""

    def encrypt(self, body: Dict[str, Any]) -> EMCLEnvelope:
        ...

    def decrypt(self, envelope: EMCLEnvelope) -> Dict[str, Any]:
        ...


def create_emcl_provider_from_env(
    *,
    default_mode: str = "aes-gcm",
    identity: Optional[str] = None,
):
    """
    Factory configuring EMCL using environment variables.

    Environment variables:
        INTENTUSNET_EMCL_ENABLED=true|false
        INTENTUSNET_EMCL_MODE=aes-gcm|simple-hmac
        INTENTUSNET_EMCL_KEY=hex or text secret
    """

    enabled = os.getenv("INTENTUSNET_EMCL_ENABLED", "true").lower() == "true"
    if not enabled:
        return None

    mode = os.getenv("INTENTUSNET_EMCL_MODE", default_mode).lower()
    key = os.getenv("INTENTUSNET_EMCL_KEY")

    if mode == "simple-hmac":
        if not key:
            raise ValueError("INTENTUSNET_EMCL_KEY is required for simple-hmac mode")
        return SimpleHMACEMCLProvider(key)

    # Default: AES-GCM 256-bit
    if not key:
        # Auto-generate dev key; production must supply a fixed one
        key = AESGCMEMCLProvider.generate_key_hex()

    return AESGCMEMCLProvider(key=key, identity=identity)
