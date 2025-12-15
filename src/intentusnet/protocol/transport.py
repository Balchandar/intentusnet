from __future__ import annotations

"""
Transport-level envelope types for IntentusNet.

These are used by all transports (HTTP, WebSocket, ZeroMQ, etc.) to wrap
IntentusNet protocol messages in a consistent outer frame.

Key ideas:
- The core *business* payloads are IntentEnvelope, AgentResponse,
  EMCLEnvelope (defined in other protocol modules).
- Transports should move TransportEnvelope instances over the wire, not
  raw intents/responses, so we can:
    - add headers (auth, tracing, node identity)
    - negotiate protocol versions
    - distinguish message kinds (intent / emcl / response / error)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class TransportEnvelope:
    """
    Top-level envelope for all transports.

    Example (JSON):

        {
          "protocol": "INTENTUSNET/1.0",
          "messageType": "intent",    # 'intent' | 'emcl' | 'response' | 'error'
          "headers": {
            "Authorization": "Bearer ...",
            "X-Intentus-Node-Id": "node-a"
          },
          "body": { ... }             # IntentEnvelope / EMCLEnvelope / AgentResponse as dict
        }

    Transports should:
      - Serialize/deserialize this object
      - Never assume what's inside `body` beyond the messageType
      - Let higher layers (gateway/runtime) interpret the body
    """

    protocol: str = "INTENTUSNET/1.0"

    # 'intent'   → body is an IntentEnvelope (dict)
    # 'emcl'     → body is an EMCLEnvelope (dict)
    # 'response' → body is an AgentResponse (dict)
    # 'error'    → optional error envelope
    messageType: str = "intent"

    # Arbitrary transport-level headers (auth, tracing, node identity, etc.)
    headers: Dict[str, Any] = field(default_factory=dict)

    # The actual business message payload, serialized to a plain dict
    body: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorEnvelope:
    """
    Optional transport-level error envelope.

    This is distinct from AgentResponse.error:

      - AgentResponse.error covers *agent / routing* errors.
      - ErrorEnvelope is for *transport / gateway* level failures
        (bad frame, auth failure, etc.) before an AgentResponse exists.
    """

    protocol: str = "INTENTUSNET/1.0"
    code: str = "TRANSPORT_ERROR"
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_exception(cls, ex: Exception, code: str = "TRANSPORT_ERROR") -> ErrorEnvelope:
        return cls(
            protocol="INTENTUSNET/1.0",
            code=code,
            message=str(ex),
            details={},
        )
