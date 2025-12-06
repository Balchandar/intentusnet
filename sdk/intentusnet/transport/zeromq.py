"""
ZeroMQ Transport for IntentusNet
--------------------------------

Supports:
- REQ/REP synchronous messaging
- Router/Dealer patterns
- EMCL encryption
"""

from __future__ import annotations
import zmq
import json
from typing import Optional, Dict, Any

from ..protocol.models import (
    IntentEnvelope,
    AgentResponse,
    TransportEnvelope,
    TransportNegotiation,
)
from ..protocol.validators import validate_transport_envelope
from ..utils.json import json_dumps, json_loads
from .base import Transport
from ..emcl.base import EMCLProvider


class ZeroMQTransport(Transport):
    """
    ZeroMQ REQ client.
    """

    def __init__(self, endpoint: str, *, emcl: Optional[EMCLProvider] = None) -> None:
        self._endpoint = endpoint
        self._emcl = emcl

        ctx = zmq.Context.instance()
        self._socket = ctx.socket(zmq.REQ)
        self._socket.connect(endpoint)

    def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        body: Dict[str, Any] = env.__dict__

        # Encrypt if needed
        if self._emcl:
            encrypted = self._emcl.encrypt(body)
            payload = encrypted.__dict__
            msg_type = "emcl"
        else:
            payload = body
            msg_type = "intent"

        envelope = TransportEnvelope(
            protocol="INTENTUSNET/1.0",
            protocolNegotiation=TransportNegotiation(minVersion="1.0", maxVersion="1.0"),
            messageType=msg_type,
            headers={},
            body=payload,
        )

        self._socket.send_string(json_dumps(envelope.__dict__))
        resp_raw = self._socket.recv_string()

        resp = json_loads(resp_raw)
        validate_transport_envelope(resp)

        if resp["messageType"] == "emcl" and self._emcl:
            decoded = self._emcl.decrypt(resp["body"])
            return AgentResponse(**decoded)

        return AgentResponse(**resp["body"])


# Server-side handler

class ZeroMQServer:
    """
    ROUTER socket server that forwards decoded envelopes to IntentRouter.
    """

    def __init__(self, endpoint: str, router, emcl: Optional[EMCLProvider] = None) -> None:
        self._endpoint = endpoint
        self._router = router
        self._emcl = emcl

        ctx = zmq.Context.instance()
        self._socket = ctx.socket(zmq.REP)
        self._socket.bind(endpoint)

    def serve_forever(self):
        while True:
            raw = self._socket.recv_string()
            obj = json_loads(raw)
            validate_transport_envelope(obj)

            if obj["messageType"] == "emcl":
                if not self._emcl:
                    raise RuntimeError("Received encrypted payload without EMCL configured.")
                decoded = self._emcl.decrypt(obj["body"])
                env = IntentEnvelope(**decoded)
            else:
                env = IntentEnvelope(**obj["body"])

            resp = self._router.route_intent(env)
            out_body = resp.__dict__

            if self._emcl:
                enc = self._emcl.encrypt(out_body)
                rep_env = {
                    "protocol": "INTENTUSNET/1.0",
                    "protocolNegotiation": {"minVersion": "1.0", "maxVersion": "1.0"},
                    "messageType": "emcl",
                    "headers": {},
                    "body": enc.__dict__,
                }
            else:
                rep_env = {
                    "protocol": "INTENTUSNET/1.0",
                    "protocolNegotiation": {"minVersion": "1.0", "maxVersion": "1.0"},
                    "messageType": "response",
                    "headers": {},
                    "body": out_body,
                }

            self._socket.send_string(json_dumps(rep_env))
