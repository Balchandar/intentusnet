"""
ZeroMQ Transport for IntentusNet

- Simple REQ/REP client transport
- Sends TransportEnvelope with IntentEnvelope (or EMCL)
- Expects TransportEnvelope with AgentResponse (or EMCL)
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict, Optional

import zmq

from intentusnet.protocol.intent import IntentEnvelope
from intentusnet.protocol.response import AgentResponse, ErrorInfo
from intentusnet.protocol.emcl import EMCLEnvelope
from intentusnet.protocol.enums import ErrorCode
from intentusnet.security.emcl.base import EMCLProvider


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


class ZeroMQTransport:
    """
    Blocking ZeroMQ REQ/REP transport.

    Usage:
        transport = ZeroMQTransport("tcp://localhost:5555", emcl=provider)
        resp = transport.send_intent(env)
    """

    def __init__(self, address: str, *, emcl: Optional[EMCLProvider] = None) -> None:
        self._address = address
        self._emcl = emcl
        self._ctx = zmq.Context.instance()
        self._socket = self._ctx.socket(zmq.REQ)
        self._socket.connect(address)

    def close(self) -> None:
        try:
            self._socket.close(0)
        except Exception:
            pass

    def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        intent_body: Dict[str, Any] = asdict(env)

        if self._emcl is not None:
            enc = self._emcl.encrypt(intent_body)
            out_env = {
                "protocol": "INTENTUSNET/1.0",
                "protocolNegotiation": {"minVersion": "1.0", "maxVersion": "1.0"},
                "messageType": "emcl",
                "headers": {},
                "body": asdict(enc),
            }
        else:
            out_env = {
                "protocol": "INTENTUSNET/1.0",
                "protocolNegotiation": {"minVersion": "1.0", "maxVersion": "1.0"},
                "messageType": "intent",
                "headers": {},
                "body": intent_body,
            }

        self._socket.send_string(_json_dumps(out_env))
        raw = self._socket.recv_string()

        decoded: Dict[str, Any] = json.loads(raw)
        msg_type = decoded.get("messageType")
        body = decoded.get("body") or {}

        if msg_type == "emcl":
            if self._emcl is None:
                raise RuntimeError("Received EMCL response but no EMCLProvider configured")
            body = self._emcl.decrypt(EMCLEnvelope(**body))

        return self._decode_agent_response(body)

    def _decode_agent_response(self, data: Dict[str, Any]) -> AgentResponse:
        error_data = data.get("error")
        error_obj: Optional[ErrorInfo] = None

        if error_data:
            code_raw = error_data.get("code") or "INTERNAL_AGENT_ERROR"
            try:
                code = ErrorCode(code_raw)
            except Exception:
                code = ErrorCode.INTERNAL_AGENT_ERROR

            error_obj = ErrorInfo(
                code=code,
                message=error_data.get("message", ""),
                retryable=error_data.get("retryable", False),
                details=error_data.get("details", {}) or {},
            )

        return AgentResponse(
            version=data.get("version", "1.0"),
            status=data.get("status", "error"),
            payload=data.get("payload"),
            metadata=data.get("metadata", {}) or {},
            error=error_obj,
        )
