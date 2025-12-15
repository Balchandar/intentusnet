from __future__ import annotations

"""
HTTP Transport for IntentusNet (PLAIN, NO EMCL)

- Sends IntentEnvelope as JSON
- Expects AgentResponse as JSON
- Used by IntentusClient or RemoteAgentProxy
"""

import json
from dataclasses import asdict
from typing import Any, Dict, Optional

import requests

from intentusnet.protocol.intent import IntentEnvelope
from intentusnet.protocol.response import AgentResponse, ErrorInfo
from intentusnet.protocol.enums import ErrorCode


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


class HTTPTransport:
    """
    Plain HTTP transport.

    POST /intent
    {
        "protocol": "INTENTUSNET/1.0",
        "messageType": "intent",
        "body": { ...IntentEnvelope... }
    }

    Response:
    {
        "protocol": "INTENTUSNET/1.0",
        "messageType": "response",
        "body": { ...AgentResponse... }
    }
    """

    def __init__(self, url: str, timeout: float = 10.0):
        self._url = url.rstrip("/")
        self._timeout = timeout
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Transport interface
    # ------------------------------------------------------------------
    def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        try:
            frame = {
                "protocol": "INTENTUSNET/1.0",
                "messageType": "intent",
                "body": asdict(env),
            }

            resp = self._session.post(
                self._url,
                data=_json_dumps(frame),
                headers={"Content-Type": "application/json"},
                timeout=self._timeout,
            )
            resp.raise_for_status()

            decoded = resp.json()

            if decoded.get("messageType") != "response":
                raise ValueError("Invalid response messageType")

            return self._decode_agent_response(decoded.get("body") or {})

        except Exception as ex:
            # IMPORTANT: transport must NEVER raise
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

    # ------------------------------------------------------------------
    # JSON → AgentResponse
    # ------------------------------------------------------------------
    def _decode_agent_response(self, data: Dict[str, Any]) -> AgentResponse:
        err = data.get("error")
        error_obj: Optional[ErrorInfo] = None

        if err:
            try:
                code = ErrorCode(err.get("code", ErrorCode.INTERNAL_AGENT_ERROR))
            except Exception:
                code = ErrorCode.INTERNAL_AGENT_ERROR

            error_obj = ErrorInfo(
                code=code,
                message=err.get("message", ""),
                retryable=err.get("retryable", False),
                details=err.get("details") or {},
            )

        return AgentResponse(
            version=data.get("version", "1.0"),
            status=data.get("status", "error"),
            payload=data.get("payload"),
            metadata=data.get("metadata") or {},
            error=error_obj,
        )
