"""
HTTP Transport for IntentusNet

- Sends IntentEnvelope as a TransportEnvelope via HTTP POST
- Optionally wraps payload with EMCL (encrypted body)
- Expects a TransportEnvelope back containing an AgentResponse or EMCL envelope
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict, Optional

import requests

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


class HTTPTransport:
    """
    Simple blocking HTTP transport.

    Usage:
        transport = HTTPTransport("http://localhost:8000/intents", emcl=provider)
        resp = transport.send_intent(env)
    """

    def __init__(
        self,
        url: str,
        *,
        emcl: Optional[EMCLProvider] = None,
        timeout: float = 10.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._emcl = emcl
        self._timeout = timeout
        self._session = session or requests.Session()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        """
        Encode IntentEnvelope -> TransportEnvelope, send via HTTP,
        decode response -> AgentResponse.
        """
        intent_body: Dict[str, Any] = asdict(env)

        if self._emcl is not None:
            enc = self._emcl.encrypt(intent_body)
            transport_env = {
                "protocol": "INTENTUSNET/1.0",
                "protocolNegotiation": {"minVersion": "1.0", "maxVersion": "1.0"},
                "messageType": "emcl",
                "headers": {},
                "body": asdict(enc),
            }
        else:
            transport_env = {
                "protocol": "INTENTUSNET/1.0",
                "protocolNegotiation": {"minVersion": "1.0", "maxVersion": "1.0"},
                "messageType": "intent",
                "headers": {},
                "body": intent_body,
            }

        response = self._session.post(
            self._url,
            data=_json_dumps(transport_env),
            headers={"Content-Type": "application/json"},
            timeout=self._timeout,
        )
        response.raise_for_status()

        decoded: Dict[str, Any] = json.loads(response.text)
        msg_type = decoded.get("messageType")
        body = decoded.get("body") or {}

        # EMCL-wrapped response
        if msg_type == "emcl":
            if self._emcl is None:
                raise RuntimeError("Received EMCL response but no EMCLProvider configured")
            body = self._emcl.decrypt(EMCLEnvelope(**body))

        return self._decode_agent_response(body)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
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
