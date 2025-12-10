"""
Identity Chain Utilities
------------------------

The EMCL identity chain tracks the sequence of agents that touched a payload.

This enables:
- provenance
- audit logging
- secure multi-hop flows
"""

from __future__ import annotations
from typing import List


def extend_identity_chain(chain: List[str], identity: str | None) -> List[str]:
    """
    Appends the calling agent/service identity to the identity chain.
    """
    if identity is None:
        return list(chain)
    return chain + [identity]

