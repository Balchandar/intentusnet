"""
WebSocket Transport for IntentusNet

- Async duplex transport
- Sends a TransportEnvelope containing an IntentEnvelope (or EMCL)
- Expects a TransportEnvelope back containing an AgentResponse (or EMCL)
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from typing import Any, Dict, Optional

import websockets

from intentusnet.protocol.models import (
    IntentEnvelope,
    AgentResponse,
    EMCLEnvelope,
    ErrorInfo,
)
from intentusnet.protocol.enums import ErrorCode
from intentusnet.security.emcl.base import EMCLProvider


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


class WebSocketTransport:
    """
    Async WebSocket transport for IntentusNet.

    Usage:
        transport = WebSocketTransport("ws://localhost:9000/ws", emcl=provider)
        resp = await transport.send_intent(env)
    """

    def __init__(self, url: str, *, emcl: Optional[EMCLProvider] = None) -> None:
        self._url = url
        self._emcl = emcl

    async def send_intent(self, env: IntentEnvelope) -> AgentResponse:
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

        async with websockets.connect(self._url) as ws:
            await ws.send(_json_dumps(out_env))
            raw = await ws.recv()

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
