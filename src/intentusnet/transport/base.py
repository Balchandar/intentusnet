from __future__ import annotations

"""
Base transport interface for all IntentusNet transports.

This defines the transport boundary:

    IntentEnvelope  → [TransportEnvelope] → remote node
    remote node     → [TransportEnvelope] → AgentResponse

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
  - security layers (JWT/EMCL)
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from intentusnet.protocol.intent import IntentEnvelope
from intentusnet.protocol.response import AgentResponse
from intentusnet.protocol.transport import TransportEnvelope


class Transport(ABC):
    """
    Abstract base class for all transports.

    Implicit contract:
        Client side:
            - send_intent(env) → AgentResponse
            - internally: env → TransportEnvelope → wire → TransportEnvelope → AgentResponse

        Server side:
            - your gateway (HTTP/ZMQ/WS) receives a TransportEnvelope JSON
            - parses messageType/body
            - uses runtime.router to produce AgentResponse
            - emits TransportEnvelope(response)
    """

    # ----------------------------------------------------------------------
    # HIGH-LEVEL API (public)
    # ----------------------------------------------------------------------
    @abstractmethod
    def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        """
        Send a business-level IntentEnvelope over this transport and return
        the resulting AgentResponse.

        Every concrete transport MUST implement this method.

        Pattern:
            env → TransportEnvelope(messageType='intent'|'emcl', body=env_dict)
                → JSON → wire → JSON → TransportEnvelope(messageType='response')
                → AgentResponse
        """
        raise NotImplementedError

    # ----------------------------------------------------------------------
    # LOW-LEVEL OPTIONAL API
    # ----------------------------------------------------------------------
    def send_frame(self, frame: TransportEnvelope) -> TransportEnvelope:
        """
        Optional low-level raw API.

        In many transports (HTTP remote agent, ZMQ, WS), this is useful.
        Default implementation raises, so subclasses override only if needed.

        For example, RemoteAgentProxy will build its own TransportEnvelope
        containing:
            {
              protocol: "INTENTUSNET/1.0",
              messageType: "intent" | "emcl",
              headers: {...},
              body: { agent, envelope }
            }

        and then call transport.send_frame(frame).
        """
        raise NotImplementedError(
            f"{self.__class__.__name__}.send_frame() not implemented"
        )
