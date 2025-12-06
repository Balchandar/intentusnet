from __future__ import annotations
from typing import Protocol, Dict, Any
from ..protocol.models import EMCLEnvelope


class EMCLProvider(Protocol):
    def encrypt(self, body: Dict[str, Any]) -> EMCLEnvelope:
        ...

    def decrypt(self, envelope: EMCLEnvelope) -> Dict[str, Any]:
        ...
