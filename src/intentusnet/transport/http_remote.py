from __future__ import annotations

from intentusnet.security.node_identity import NodeSigner

"""
HTTP transport used by RemoteAgentProxy to call a remote IntentusNet node.

This transport talks to a *node execution gateway* endpoint, typically:

    POST {base_url}/execute-agent

Contract (over the wire):

  Request (TransportEnvelope JSON)
  --------------------------------
  {
    "protocol": "INTENTUSNET/1.0",
    "messageType": "intent" | "emcl",
    "headers": {
      "Authorization": "Bearer ...",            # optional JWT forwarding
      "X-Intentus-Node-Id": "...",             # optional node-to-node auth (future)
      "X-Intentus-Node-Signature": "..."       # optional node-to-node auth (future)
    },
    "body": {
      "agent": "agent-name",
      "envelope": { ... IntentEnvelope or EMCLEnvelope ... }
    }
  }

  Response (TransportEnvelope JSON)
  ---------------------------------
  {
    "protocol": "INTENTUSNET/1.0",
    "messageType": "response" | "emcl" | "error",
    "headers": {},
    "body": { ... AgentResponse or EMCLEnvelope or ErrorEnvelope ... }
  }

EMCL and node-to-node auth are handled via injectable collaborators:

  - emcl_provider: object with encrypt(dict) -> EMCLEnvelope, decrypt(dict) -> dict
  - jwt_forwarder: callable returning "Bearer ..." string if available

This keeps the transport focused purely on HTTP and envelopes.
"""

import dataclasses
import json
from typing import Any, Dict, Optional

import requests

from intentusnet.transport.base import Transport
from intentusnet.protocol.intent import IntentEnvelope
from intentusnet.protocol.response import AgentResponse, ErrorInfo
from intentusnet.protocol.transport import TransportEnvelope


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


class HTTPRemoteAgentTransport(Transport):
    """
    HTTP transport dedicated to remote agent execution.

    Typical usage:

        transport = HTTPRemoteAgentTransport(
            base_url="http://node-b:8000",
            agent_name="web-search-agent",
            emcl_provider=emcl,        # optional
            jwt_forwarder=get_jwt,     # optional
        )

        proxy = RemoteAgentProxy(router, "web-search-agent", "node-b", transport)
        runtime.registry.register(proxy)

    The remote node is expected to expose an HTTP endpoint:

        POST /execute-agent

    which understands the TransportEnvelope / body format described above.
    """

    def __init__(
        self,
        base_url: str,
        agent_name: str,
        *,
        timeout: float = 10.0,
        session: Optional[requests.Session] = None,
        emcl_provider: Optional[Any] = None,
        jwt_forwarder: Optional[callable] = None,
        node_signer: Optional[NodeSigner] = None,     
    ) -> None:
        """
        :param base_url: Base URL of the remote node (e.g. http://node-b:8000)
        :param agent_name: Name of the agent on the remote node to invoke
        :param timeout: HTTP request timeout in seconds
        :param session: Optional custom requests.Session
        :param emcl_provider: Optional EMCL provider (encrypt/decrypt)
        :param jwt_forwarder: Optional callable that returns a JWT string
                               (without the 'Bearer ' prefix) to forward.
        """
        self._url = base_url.rstrip("/") + "/execute-agent"
        self._agent_name = agent_name
        self._timeout = timeout
        self._session = session or requests.Session()
        self._emcl = emcl_provider
        self._jwt_forwarder = jwt_forwarder
        self._node_signer = node_signer 

    # ------------------------------------------------------------------
    # High-level API
    # ------------------------------------------------------------------
    def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        """
        Convert IntentEnvelope -> TransportEnvelope, POST to remote node,
        parse TransportEnvelope -> AgentResponse.
        """
        env_dict: Dict[str, Any] = dataclasses.asdict(env)

        # Choose messageType & body payload based on EMCL
        if self._emcl is not None:
            enc = self._emcl.encrypt(env_dict)
            envelope_body = enc.__dict__
            msg_type = "emcl"
        else:
            envelope_body = env_dict
            msg_type = "intent"

        frame = TransportEnvelope(
            protocol="INTENTUSNET/1.0",
            messageType=msg_type,
            headers={},
            body={
                "agent": self._agent_name,
                "envelope": envelope_body,
            },
        )

        # Use low-level frame send to keep logic unified
        resp_frame = self.send_frame(frame)

        # Decode AgentResponse from returned frame
        if resp_frame.messageType == "emcl":
            if self._emcl is None:
                raise RuntimeError("Remote node returned EMCL response but no emcl_provider configured")
            decrypted: Dict[str, Any] = self._emcl.decrypt(resp_frame.body)
            return self._decode_agent_response(decrypted)

        if resp_frame.messageType == "response":
            return self._decode_agent_response(resp_frame.body)

        if resp_frame.messageType == "error":
            # Transport-level error envelope -> convert to AgentResponse with error
            return self._error_response_from_transport(resp_frame)

        # Unknown messageType
        return AgentResponse(
            version="1.0",
            status="error",
            payload=None,
            metadata={"transport": "http-remote", "messageType": resp_frame.messageType},
            error=ErrorInfo(
                code="REMOTE_TRANSPORT_ERROR",
                message=f"Unexpected messageType '{resp_frame.messageType}' from remote node",
                retryable=False,
                details={},
            ),
        )

    # ------------------------------------------------------------------
    # Low-level frame send
    # ------------------------------------------------------------------
    def send_frame(self, frame: TransportEnvelope) -> TransportEnvelope:
        """
        Serialize TransportEnvelope to JSON, send via HTTP POST, parse returned frame.
        """
        payload_str = _json_dumps({
            "protocol": frame.protocol,
            "messageType": frame.messageType,
            "headers": frame.headers,
            "body": frame.body,
        })
        body_bytes = payload_str.encode("utf-8")

        headers: Dict[str, str] = {"Content-Type": "application/json"}

        # Optional JWT forwarding
        if self._jwt_forwarder is not None:
            token = self._jwt_forwarder()
            if token:
                if token.startswith("Bearer "):
                    headers["Authorization"] = token
                else:
                    headers["Authorization"] = f"Bearer {token}"

        # NOTE: Node-to-node HMAC signing can be added here later by
        
        # injecting a signer and updating headers accordingly.
        if self._node_signer is not None:
            signature_headers = self._node_signer.sign(body_bytes)
            headers.update(signature_headers)
            
        response = self._session.post(
            self._url,
            data=body_bytes,
            headers=headers,
            timeout=self._timeout,
        )
        response.raise_for_status()

        try:
            decoded = response.json()
        except Exception as ex:  # pragma: no cover - defensive
            # Wrap non-JSON responses into a synthetic error frame
            return TransportEnvelope(
                protocol="INTENTUSNET/1.0",
                messageType="error",
                headers={},
                body={
                    "code": "REMOTE_TRANSPORT_ERROR",
                    "message": f"Invalid JSON from remote node: {ex}",
                    "details": {"status_code": response.status_code},
                },
            )

        return TransportEnvelope(
            protocol=decoded.get("protocol", "INTENTUSNET/1.0"),
            messageType=decoded.get("messageType", "response"),
            headers=decoded.get("headers") or {},
            body=decoded.get("body") or {},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _decode_agent_response(self, data: Dict[str, Any]) -> AgentResponse:
        """
        Convert a plain dict into AgentResponse + ErrorInfo.
        """
        error_data = data.get("error")
        error_obj: Optional[ErrorInfo] = None

        if error_data:
            # Be defensive: allow string codes or missing fields
            code = error_data.get("code") or "INTERNAL_AGENT_ERROR"
            message = error_data.get("message", "")
            retryable = bool(error_data.get("retryable", False))
            details = error_data.get("details") or {}
            error_obj = ErrorInfo(
                code=code,
                message=message,
                retryable=retryable,
                details=details,
            )

        return AgentResponse(
            version=data.get("version", "1.0"),
            status=data.get("status", "error"),
            payload=data.get("payload"),
            metadata=data.get("metadata", {}) or {},
            error=error_obj,
        )

    def _error_response_from_transport(self, frame: TransportEnvelope) -> AgentResponse:
        """
        Turn a transport-level error envelope into an AgentResponse that
        the caller can treat as a normal error.
        """
        body = frame.body or {}
        code = body.get("code") or "REMOTE_TRANSPORT_ERROR"
        message = body.get("message") or "Remote transport error"
        details = body.get("details") or {}

        return AgentResponse(
            version="1.0",
            status="error",
            payload=None,
            metadata={"transport": "http-remote"},
            error=ErrorInfo(
                code=code,
                message=message,
                retryable=False,
                details=details,
            ),
        )
