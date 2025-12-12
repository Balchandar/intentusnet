from __future__ import annotations

"""
IntentusNet Node Execution Gateway (HTTP)

This example exposes a remote node that can execute agents for other nodes.

Contract (matches HTTPRemoteAgentTransport):

  POST /execute-agent
  -------------------
  Request body: TransportEnvelope JSON

    {
      "protocol": "INTENTUSNET/1.0",
      "messageType": "intent" | "emcl",
      "headers": { ... },                # optional, e.g. auth / tracing
      "body": {
        "agent": "agent-name",
        "envelope": { ... }              # IntentEnvelope OR EMCLEnvelope as dict
      }
    }

  Response body: TransportEnvelope JSON

    {
      "protocol": "INTENTUSNET/1.0",
      "messageType": "response" | "emcl" | "error",
      "headers": {},
      "body": { ... AgentResponse / EMCLEnvelope / ErrorEnvelope ... }
    }

Security:
  - Node-to-node HMAC signing (NodeVerifier) validates callers.
  - If invalid/missing signature → 401.

EMCL:
  - If EMCL_PROVIDER is configured, this gateway will decrypt incoming
    EMCL envelopes and optionally re-encrypt responses.
"""

import dataclasses
import json
import logging
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request

from intentusnet.core.runtime import IntentusRuntime
from intentusnet.protocol.intent import IntentEnvelope
from intentusnet.protocol.response import AgentResponse
from intentusnet.protocol.transport import TransportEnvelope, ErrorEnvelope
from intentusnet.protocol.validators import validate_intent_envelope
from intentusnet.security.node_identity import NodeIdentity, NodeVerifier

logger = logging.getLogger("intentusnet.node-gateway")

app = FastAPI(title="IntentusNet Node Execution Gateway", version="0.1.0")

# ------------------------------------------------------------------------------
# Runtime setup
# ------------------------------------------------------------------------------

# Create a local runtime on THIS node.
runtime = IntentusRuntime()

# Optional: EMCL provider (if your runtime exposes one)
EMCL_PROVIDER = getattr(runtime, "emcl_provider", None)

# Node identity for THIS node (example values; use config/env in real deploy)
NODE_IDENTITY = NodeIdentity(
    nodeId="node-b",               # unique ID for this node
    sharedSecret="super-secret",   # shared symmetric key for HMAC
)
NODE_VERIFIER = NodeVerifier(NODE_IDENTITY)


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def _agent_response_to_dict(resp: AgentResponse) -> Dict[str, Any]:
    """
    Convert AgentResponse dataclass into a plain dict for JSON encoding.
    """
    return dataclasses.asdict(resp)


def _make_error_frame(code: str, message: str, details: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Build a transport-level error envelope as a plain dict.
    """
    err = ErrorEnvelope(
        code=code,
        message=message,
        details=details or {},
    )
    return {
        "protocol": err.protocol,
        "messageType": "error",
        "headers": {},
        "body": {
            "code": err.code,
            "message": err.message,
            "details": err.details,
        },
    }


# ------------------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------------------

@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/execute-agent")
async def execute_agent(request: Request) -> Dict[str, Any]:
    """
    Execute a specific agent on this node based on the given TransportEnvelope.

    Expected frame:
        {
          "protocol": "INTENTUSNET/1.0",
          "messageType": "intent" | "emcl",
          "headers": { ... },
          "body": {
            "agent": "agent-name",
            "envelope": { ... }
          }
        }
    """
    # --------------------------------------------------------------------------
    # Node-to-node signature verification
    # --------------------------------------------------------------------------
    raw_bytes = await request.body()

    if not NODE_VERIFIER.verify(request.headers, raw_bytes):
        # Do NOT leak details; just say unauthorized.
        raise HTTPException(status_code=401, detail="Invalid or missing node signature")

    # --------------------------------------------------------------------------
    # Parse JSON into TransportEnvelope
    # --------------------------------------------------------------------------
    try:
        frame_json = json.loads(raw_bytes.decode("utf-8"))
    except Exception as ex:
        logger.exception("Invalid JSON envelope: %s", ex)
        raise HTTPException(status_code=400, detail="Invalid JSON envelope")

    try:
        env = TransportEnvelope(
            protocol=frame_json.get("protocol", "INTENTUSNET/1.0"),
            messageType=frame_json.get("messageType", "intent"),
            headers=frame_json.get("headers") or {},
            body=frame_json.get("body") or {},
        )
    except Exception as ex:
        logger.exception("Invalid transport envelope: %s", ex)
        raise HTTPException(status_code=400, detail="Invalid transport envelope")

    msg_type = env.messageType
    body = env.body or {}
    agent_name = body.get("agent")
    envelope_data = body.get("envelope") or {}

    if not agent_name:
        raise HTTPException(status_code=400, detail="Missing 'agent' in body")

    # --------------------------------------------------------------------------
    # EMCL handling (optional)
    # --------------------------------------------------------------------------
    if msg_type == "emcl":
        if EMCL_PROVIDER is None:
            # This node does not support EMCL but received an EMCL frame.
            return _make_error_frame(
                code="EMCL_NOT_SUPPORTED",
                message="EMCL envelope received but EMCL is not configured on this node",
                details={},
            )
        try:
            envelope_data = EMCL_PROVIDER.decrypt(envelope_data)
        except Exception as ex:
            logger.exception("Failed to decrypt EMCL envelope: %s", ex)
            return _make_error_frame(
                code="EMCL_DECRYPT_FAILED",
                message=str(ex),
                details={},
            )

    # --------------------------------------------------------------------------
    # Validate and build IntentEnvelope
    # --------------------------------------------------------------------------
    try:
        validate_intent_envelope(envelope_data)
    except Exception as ex:
        logger.exception("Invalid IntentEnvelope data: %s", ex)
        return _make_error_frame(
            code="INVALID_INTENT_ENVELOPE",
            message=str(ex),
            details={},
        )

    try:
        intent_env = IntentEnvelope(**envelope_data)
    except Exception as ex:
        logger.exception("Failed to construct IntentEnvelope: %s", ex)
        return _make_error_frame(
            code="INTENT_ENVELOPE_CONSTRUCTION_FAILED",
            message=str(ex),
            details={},
        )

    # Ensure we direct routing to a specific agent if not already set
    if not intent_env.routing.targetAgent:
        intent_env.routing.targetAgent = agent_name

    # --------------------------------------------------------------------------
    # Execute via local router
    # --------------------------------------------------------------------------
    try:
        response: AgentResponse = runtime.router.route_intent(intent_env)
    except Exception as ex:
        logger.exception("Router execution failed: %s", ex)
        return _make_error_frame(
            code="ROUTING_ERROR",
            message=str(ex),
            details={},
        )

    resp_dict = _agent_response_to_dict(response)

    # --------------------------------------------------------------------------
    # Optional EMCL wrapping for response
    # --------------------------------------------------------------------------
    if EMCL_PROVIDER is not None and msg_type == "emcl":
        try:
            encrypted = EMCL_PROVIDER.encrypt(resp_dict)
            return {
                "protocol": "INTENTUSNET/1.0",
                "messageType": "emcl",
                "headers": {},
                "body": dataclasses.asdict(encrypted),
            }
        except Exception as ex:
            logger.exception("Failed to encrypt EMCL response: %s", ex)
            return _make_error_frame(
                code="EMCL_ENCRYPT_FAILED",
                message=str(ex),
                details={},
            )

    # Plain response
    return {
        "protocol": "INTENTUSNET/1.0",
        "messageType": "response",
        "headers": {},
        "body": resp_dict,
    }
