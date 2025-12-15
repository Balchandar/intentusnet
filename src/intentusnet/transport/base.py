from __future__ import annotations

"""
Base transport interface for all IntentusNet transports.

This defines the transport boundary:

    IntentEnvelope  → TransportEnvelope → remote node
    remote node     → TransportEnvelope → AgentResponse

Transports DO NOT:
  - interpret intents
  - implement routing
  - apply policy
  - validate envelopes
  - decrypt EMCL themselves (gateway/runtime layer does that)

Transports ONLY:
  - serialize TransportEnvelope
  - deliver to remote endpoint
  - deserialize TransportEnvelope

Everything else is handled by:
  - runtime
  - router
  - gateway
  - security layers (JWT / EMCL)
"""

from typing import Protocol

from intentusnet.protocol.intent import IntentEnvelope
from intentusnet.protocol.response import AgentResponse
from intentusnet.protocol.transport import TransportEnvelope


class Transport(Protocol):
    """
    Transport interface for IntentusNet.

    Implementations may include:
      - In-process transport
      - HTTP transport
      - WebSocket transport
      - ZeroMQ transport
      - MCP adapter transport

    This is a *capability interface* (Protocol), not a base class.
    """

    # ------------------------------------------------------------------
    # HIGH-LEVEL API (required)
    # ------------------------------------------------------------------
    def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        """
        Send a business-level IntentEnvelope over this transport
        and return the resulting AgentResponse.

        Required for all transports.

        Typical flow:
            IntentEnvelope
              → TransportEnvelope(messageType="intent" | "emcl")
              → wire (JSON / binary)
              → TransportEnvelope(messageType="response")
              → AgentResponse
        """
        ...

    # ------------------------------------------------------------------
    # LOW-LEVEL API (optional)
    # ------------------------------------------------------------------
    def send_frame(self, frame: TransportEnvelope) -> TransportEnvelope:
        """
        Optional low-level raw transport API.

        Useful for:
          - RemoteAgentProxy
          - Gateways
          - EMCL-wrapped frames
          - Custom protocol adapters (e.g., MCP)

        Implementations MAY raise NotImplementedError
        if they only support send_intent().
        """
        ...
