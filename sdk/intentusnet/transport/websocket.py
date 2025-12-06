"""
WebSocket Transport for IntentusNet
-----------------------------------

Duplex transport supporting:
- continuous message streams
- async send/receive
- EMCL encryption
"""

from __future__ import annotations
import asyncio
import json
import websockets
from typing import Optional, Dict, Any

from ..protocol.models import (
    IntentEnvelope,
    AgentResponse,
    TransportEnvelope,
    TransportNegotiation,
)
from ..protocol.validators import validate_transport_envelope
from ..utils.json import json_dumps, json_loads
from ..emcl.base import EMCLProvider
from .base import Transport


class WebSocketTransport(Transport):
    """
    Async WebSocket client for IntentusNet.
    """

    def __init__(self, uri: str, *, emcl: Optional[EMCLProvider] = None):
        self._uri = uri
        self._emcl = emcl

    async def _send(self, env: IntentEnvelope) -> AgentResponse:
        body = env.__dict__

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

        async with websockets.connect(self._uri) as ws:
            await ws.send(json_dumps(envelope.__dict__))
            resp_raw = await ws.recv()

        resp = json_loads(resp_raw)
        validate_transport_envelope(resp)

        if resp["messageType"] == "emcl" and self._emcl:
            decoded = self._emcl.decrypt(resp["body"])
            return AgentResponse(**decoded)

        return AgentResponse(**resp["body"])

    # Sync wrapper (just for API compatibility)
    def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        return asyncio.get_event_loop().run_until_complete(self._send(env))


# Server-side handler

async def websocket_server_handler(websocket, path, router, emcl: Optional[EMCLProvider]):
    raw = await websocket.recv()
    obj = json_loads(raw)
    validate_transport_envelope(obj)

    if obj["messageType"] == "emcl" and emcl:
        decoded = emcl.decrypt(obj["body"])
        env = IntentEnvelope(**decoded)
    else:
        env = IntentEnvelope(**obj["body"])

    resp = router.route_intent(env)
    out_body = resp.__dict__

    if emcl:
        encrypted = emcl.encrypt(out_body)
        out_env = {
            "protocol": "INTENTUSNET/1.0",
            "protocolNegotiation": {"minVersion": "1.0", "maxVersion": "1.0"},
            "messageType": "emcl",
            "headers": {},
            "body": encrypted.__dict__,
        }
    else:
        out_env = {
            "protocol": "INTENTUSNET/1.0",
            "protocolNegotiation": {"minVersion": "1.0", "maxVersion": "1.0"},
            "messageType": "response",
            "headers": {},
            "body": out_body,
        }

    await websocket.send(json_dumps(out_env))
