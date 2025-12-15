"""
Identity Chain Utilities
------------------------

The EMCL identity chain tracks the sequence of actors that touched a payload.
"""

from __future__ import annotations

from typing import List, Optional


def extend_identity_chain(chain: List[str], identity: Optional[str]) -> List[str]:
    """
    Append the current identity to the chain, preserving ordering.
    """
    if identity is None:
        return list(chain)
    return chain + [identity]
