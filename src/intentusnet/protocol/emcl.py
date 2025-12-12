from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class EMCLEnvelope:
    """
    EMCL-encrypted payload wrapper.

    Fields are intentionally minimal here; crypto providers
    can extend/interpret as needed.
    """
    cipherText: str
    iv: str
    tag: str
    identityChain: List[str] = field(default_factory=list)
