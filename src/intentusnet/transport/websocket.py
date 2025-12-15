from __future__ import annotations

"""
WebSocket Transport for IntentusNet (SYNC, v1)

- Synchronous transport
- Sends TransportEnvelope containing IntentEnvelope (or EMCL)
- Expects TransportEnvelope containing AgentResponse (or EMCL)
"""

import json
from dataclasses import asdict
from typing import Any, Dict, Optional

from websockets.sync.client import connect

from intentusnet.protocol.intent import IntentEnvelope
from intentusnet.protocol.response import AgentResponse, ErrorInfo
from intentusnet.protocol.emcl import EMCLEnvelope
from intentusnet.protocol.enums import ErrorCode
from intentusnet.security.emcl.base import EMCLProvider


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


class WebSocketTransport:
    """
    Synchronous WebSocket transport for IntentusNet (v1).
    """

    def __init__(self, url: str, *, emcl: Optional[EMCLProvider] = None, timeout: float = 10.0) -> None:
        self._url = url
        self._emcl = emcl
        self._timeout = timeout

    def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        try:
            body = asdict(env)

            if self._emcl is not None:
                enc = self._emcl.encrypt(body)
                frame = {
                    "protocol": "INTENTUSNET/1.0",
                    "messageType": "emcl",
                    "headers": {},
                    "body": asdict(enc),
                }
            else:
                frame = {
                    "protocol": "INTENTUSNET/1.0",
                    "messageType": "intent",
                    "headers": {},
                    "body": body,
                }

            with connect(self._url, open_timeout=self._timeout) as ws:
                ws.send(_json_dumps(frame))
                raw = ws.recv()

            decoded: Dict[str, Any] = json.loads(raw)
            msg_type = decoded.get("messageType")
            data = decoded.get("body") or {}

            if msg_type == "emcl":
                if self._emcl is None:
                    raise ValueError("EMCL response but no EMCL provider configured")
                data = self._emcl.decrypt(EMCLEnvelope(**data))

            return self._decode_agent_response(data)

        except Exception as ex:
            return AgentResponse(
                version="1.0",
                status="error",
                payload=None,
                metadata={},
                error=ErrorInfo(
                    code=ErrorCode.TRANSPORT_ERROR,
                    message=str(ex),
                    retryable=True,
                    details={},
                ),
            )

    def _decode_agent_response(self, data: Dict[str, Any]) -> AgentResponse:
        error_data = data.get("error")
        error_obj: Optional[ErrorInfo] = None

        if error_data:
            try:
                code = ErrorCode(error_data.get("code", ErrorCode.INTERNAL_AGENT_ERROR))
            except Exception:
                code = ErrorCode.INTERNAL_AGENT_ERROR

            error_obj = ErrorInfo(
                code=code,
                message=error_data.get("message", ""),
                retryable=error_data.get("retryable", False),
                details=error_data.get("details") or {},
            )

        return AgentResponse(
            version=data.get("version", "1.0"),
            status=data.get("status", "error"),
            payload=data.get("payload"),
            metadata=data.get("metadata") or {},
            error=error_obj,
        )
