from __future__ import annotations

from typing import Protocol, Dict, Any

from intentusnet.protocol.emcl import EMCLEnvelope


class EMCLProvider(Protocol):
    """
    EMCL provider interface.

    Implementations must:
    - encrypt() → wrap a JSON-serializable body into an EMCLEnvelope
    - decrypt() → restore original body dict from EMCLEnvelope
    """

    def encrypt(self, body: Dict[str, Any]) -> EMCLEnvelope:
        ...

    def decrypt(self, envelope: EMCLEnvelope) -> Dict[str, Any]:
        ...
