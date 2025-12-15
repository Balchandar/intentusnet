from __future__ import annotations

"""
ZeroMQ Transport for IntentusNet (v1)

- Blocking REQ/REP client transport
- Synchronous
- Safe failure (never raises)
- Optional EMCL support
"""

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
    """

    def __init__(
        self,
        address: str,
        *,
        emcl: Optional[EMCLProvider] = None,
        timeout_ms: int = 10_000,
    ) -> None:
        self._address = address
        self._emcl = emcl
        self._ctx = zmq.Context.instance()
        self._socket = self._ctx.socket(zmq.REQ)
        self._socket.connect(address)

        # IMPORTANT: prevent infinite blocking
        self._socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
        self._socket.setsockopt(zmq.SNDTIMEO, timeout_ms)

    def close(self) -> None:
        try:
            self._socket.close(0)
        except Exception:
            pass

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

            self._socket.send_string(_json_dumps(frame))
            raw = self._socket.recv_string()

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
