from __future__ import annotations

"""
Node-level Zero Trust Security for IntentusNet (HMAC-based)

This module implements:
  - NodeIdentity: identifies a node in a cluster.
  - NodeSigner: signs outbound frames using HMAC-SHA256.
  - NodeVerifier: validates inbound signatures.

Purpose:
  - Prevent fake / unknown nodes from calling /execute-agent.
  - Ensure integrity of TransportEnvelope frames.
  - Provide a basis for future public-key node identity (optional).

This is intentionally simple, fast, and deployable in real systems.
"""

import time
import hmac
import hashlib
from dataclasses import dataclass
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Node identity metadata
# ---------------------------------------------------------------------------

@dataclass
class NodeIdentity:
    """
    Identity for a node in an IntentusNet cluster.

    nodeId:
        Unique string (e.g. "node-a")
    sharedSecret:
        Symmetric key used for HMAC signing
    """
    nodeId: str
    sharedSecret: str


# ---------------------------------------------------------------------------
# Node signer
# ---------------------------------------------------------------------------

class NodeSigner:
    """
    Used by outbound requests to remote nodes.
    Produces:
        X-Intentus-Node-Id
        X-Intentus-Node-Ts
        X-Intentus-Node-Signature
    """

    def __init__(self, identity: NodeIdentity, *, ttl_seconds: int = 60):
        self._identity = identity
        self._ttl = ttl_seconds

    def sign(self, body_bytes: bytes) -> Dict[str, str]:
        """
        Sign outgoing frame body using:
           SIG = HMAC(sharedSecret, ts + "." + body)
        """
        ts = str(int(time.time()))
        msg = ts.encode("utf-8") + b"." + body_bytes

        sig = hmac.new(
            self._identity.sharedSecret.encode("utf-8"),
            msg,
            hashlib.sha256,
        ).hexdigest()

        return {
            "X-Intentus-Node-Id": self._identity.nodeId,
            "X-Intentus-Node-Ts": ts,
            "X-Intentus-Node-Signature": sig,
        }


# ---------------------------------------------------------------------------
# Node verifier
# ---------------------------------------------------------------------------

class NodeVerifier:
    """
    Validates signatures on inbound frames.

    NOTE:
      The verifier must hold the *same sharedSecret* as the signer.
      In production, this can come from:
         - Vault / secret manager
         - KMS-managed symmetric keys
         - Rotated keys via config
    """

    def __init__(self, identity: NodeIdentity, *, ttl_seconds: int = 60):
        self._identity = identity
        self._ttl = ttl_seconds

    def verify(self, headers: Dict[str, str], body_bytes: bytes) -> bool:
        """
        Returns True if valid, else False.
        """

        node_id = headers.get("X-Intentus-Node-Id")
        ts = headers.get("X-Intentus-Node-Ts")
        sig = headers.get("X-Intentus-Node-Signature")

        if not (node_id and ts and sig):
            return False

        if node_id != self._identity.nodeId:
            return False

        # Check timestamp freshness
        now = int(time.time())
        try:
            ts_int = int(ts)
        except ValueError:
            return False

        if abs(now - ts_int) > self._ttl:
            return False

        # Compute expected signature
        msg = ts.encode("utf-8") + b"." + body_bytes
        expected = hmac.new(
            self._identity.sharedSecret.encode("utf-8"),
            msg,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, sig)
