"""
Secure HTTP Transport for IntentusNet (EMCL-ENABLED)

- Automatically encrypts outgoing IntentEnvelope
- Automatically decrypts incoming AgentResponse
- No change required in client or runtime code
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Dict, Any

import requests

from intentusnet.protocol.emcl import EMCLEnvelope
from intentusnet.protocol.validators import (
    validate_intent_envelope,
    validate_agent_response,
)
from intentusnet.protocol.errors import EMCLValidationError
from intentusnet.security.emcl.base import EMCLProvider

from intentusnet.protocol.intent import IntentEnvelope
from intentusnet.protocol.response import AgentResponse, ErrorInfo
from intentusnet.protocol.enums import ErrorCode


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


class SecureHTTPTransport:
    """
    Wraps HTTP transport with EMCL encryption.

    The client ALWAYS works with:
        IntentEnvelope → AgentResponse

    Encryption/decryption is fully automatic.
    """

    def __init__(self, url: str, provider: EMCLProvider, timeout: float = 10.0):
        self._url = url.rstrip("/")
        self._provider = provider
        self._timeout = timeout
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Main API for IntentusClient
    # ------------------------------------------------------------------
    def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        # Convert to dict for schema validation
        env_dict = asdict(env)
        validate_intent_envelope(env_dict)

        # Encrypt
        encrypted_env = asdict(self._provider.encrypt(env_dict))

        frame = {
            "messageType": "emcl",
            "protocol": "INTENTUSNET/1.0",
            "body": encrypted_env,
        }

        # Send to gateway
        response = self._session.post(
            self._url,
            data=_json_dumps(frame),
            headers={"Content-Type": "application/json"},
            timeout=self._timeout,
        )
        response.raise_for_status()

        decoded = json.loads(response.text)

        if decoded.get("messageType") != "emcl":
            raise EMCLValidationError("Expected EMCL response frame")

        # Decode/decrypt body
        envelope = EMCLEnvelope(**decoded["body"])
        decrypted_dict = self._provider.decrypt(envelope)

        validate_agent_response(decrypted_dict)

        return self._decode_agent_response(decrypted_dict)

    # ------------------------------------------------------------------
    def _decode_agent_response(self, data: Dict[str, Any]) -> AgentResponse:
        err = data.get("error")
        error_obj: ErrorInfo | None = None

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
