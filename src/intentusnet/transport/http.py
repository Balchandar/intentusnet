"""
HTTP Transport for IntentusNet (PLAIN, NO EMCL)

- Sends IntentEnvelope as JSON
- Expects AgentResponse as JSON
- Used by IntentusClient (local or remote)
"""

from __future__ import annotations

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
    Sends plaintext IntentEnvelope to a remote HTTP gateway.
    The remote gateway must accept POST /intent with a JSON body:

        { "messageType": "intent", "body": { ...IntentEnvelope... } }

    And return:

        { "messageType": "response", "body": { ...AgentResponse... } }
    """

    def __init__(self, url: str, timeout: float = 10.0):
        self._url = url.rstrip("/")
        self._timeout = timeout
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Main API called by IntentusClient
    # ------------------------------------------------------------------
    def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        env_dict = asdict(env)

        frame = {
            "messageType": "intent",
            "protocol": "INTENTUSNET/1.0",
            "body": env_dict,
        }

        response = self._session.post(
            self._url,
            data=_json_dumps(frame),
            headers={"Content-Type": "application/json"},
            timeout=self._timeout,
        )
        response.raise_for_status()

        decoded = json.loads(response.text)

        msg_type = decoded.get("messageType")
        if msg_type != "response":
            raise RuntimeError(f"HTTPTransport: expected response, got {msg_type}")

        return self._decode_agent_response(decoded.get("body") or {})

    # ------------------------------------------------------------------
    # Convert JSON → AgentResponse dataclass
    # ------------------------------------------------------------------
    def _decode_agent_response(self, data: Dict[str, Any]) -> AgentResponse:
        err = data.get("error")
        error_obj: Optional[ErrorInfo] = None

        if err:
            try:
                code = ErrorCode(err.get("code", "INTERNAL_AGENT_ERROR"))
            except Exception:
                code = ErrorCode.INTERNAL_AGENT_ERROR

            error_obj = ErrorInfo(
                code=code,
                message=err.get("message", ""),
                retryable=err.get("retryable", False),
                details=err.get("details", {}) or {},
            )

        return AgentResponse(
            version=data.get("version", "1.0"),
            status=data.get("status", "error"),
            payload=data.get("payload"),
            metadata=data.get("metadata", {}),
            error=error_obj,
        )

class HTTPRemoteAgentTransport(Transport):
    def __init__(self, base_url: str, agent_name: str):
        self._url = base_url.rstrip("/") + "/execute-agent"
        self._agent_name = agent_name
        self._session = requests.Session()

    def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        payload = {
            "agent": self._agent_name,
            "envelope": dataclasses.asdict(env),
        }
        resp = self._session.post(self._url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return AgentResponse(**data)
