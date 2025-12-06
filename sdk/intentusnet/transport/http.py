"""
HTTP Transport for IntentusNet
------------------------------

Supports:
- HTTP POST sending of IntentEnvelope
- Optional EMCL encryption
- Receiving webhook utilities
"""

from __future__ import annotations
import requests
import json
from typing import Any, Dict, Optional

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


class HTTPTransport(Transport):
    """
    HTTP POST Transport.
    """

    def __init__(
        self,
        endpoint_url: str,
        *,
        emcl: Optional[EMCLProvider] = None,
        timeout: float = 10.0,
    ) -> None:
        self._endpoint = endpoint_url
        self._emcl = emcl
        self._timeout = timeout

    # Client → remote

    def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        body: Dict[str, Any] = env.__dict__

        # EMCL layer
        if self._emcl:
            encrypted = self._emcl.encrypt(body)
            payload = encrypted.__dict__
            message_type = "emcl"
        else:
            payload = body
            message_type = "intent"

        envelope = TransportEnvelope(
            protocol="INTENTUSNET/1.0",
            protocolNegotiation=TransportNegotiation(minVersion="1.0", maxVersion="1.0"),
            messageType=message_type,
            headers={},
            body=payload,
        )

        data = json_dumps(envelope.__dict__)
        response = requests.post(self._endpoint, data=data, timeout=self._timeout)

        if response.status_code != 200:
            raise RuntimeError(f"HTTP transport failed: {response.status_code}")

        resp_json = json_loads(response.text)
        validate_transport_envelope(resp_json)

        # unwrap EMCL if needed
        if resp_json["messageType"] == "emcl" and self._emcl:
            decrypted = self._emcl.decrypt(resp_json["body"])
            return AgentResponse(**decrypted)

        return AgentResponse(**resp_json["body"])


# Receiver (server-side utility)

def handle_http_transport_request(
    raw_json: str,
    router,
    emcl: Optional[EMCLProvider] = None,
) -> str:
    """
    Handles an incoming TransportEnvelope (HTTP POST body).
    Returns a JSON response string.

    Suitable for use inside Flask/FastAPI.
    """
    obj = json_loads(raw_json)
    validate_transport_envelope(obj)

    msg_type = obj["messageType"]
    body = obj["body"]

    if msg_type == "emcl":
        if not emcl:
            raise RuntimeError("Received EMCL payload but no EMCL provider configured.")
        decoded = emcl.decrypt(body)
        env = IntentEnvelope(**decoded)
    else:
        env = IntentEnvelope(**body)

    resp = router.route_intent(env)

    # Outgoing envelope
    out_body = resp.__dict__
    if emcl:
        enc = emcl.encrypt(out_body)
        return json_dumps(
            {
                "protocol": "INTENTUSNET/1.0",
                "protocolNegotiation": {"minVersion": "1.0", "maxVersion": "1.0"},
                "messageType": "emcl",
                "headers": {},
                "body": enc.__dict__,
            }
        )
    else:
        return json_dumps(
            {
                "protocol": "INTENTUSNET/1.0",
                "protocolNegotiation": {"minVersion": "1.0", "maxVersion": "1.0"},
                "messageType": "response",
                "headers": {},
                "body": out_body,
            }
        )
