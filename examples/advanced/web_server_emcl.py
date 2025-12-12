from __future__ import annotations

import json
import os
import datetime as dt
import uuid
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from intentusnet.core.runtime import IntentusRuntime
from intentusnet.protocol.intent import (
    IntentEnvelope,
    IntentRef,
    IntentContext,
    IntentMetadata,
    RoutingOptions,
    RoutingMetadata,
)
from intentusnet.protocol.response import AgentResponse
from intentusnet.protocol.emcl import EMCLEnvelope
from intentusnet.protocol.validators import (
    validate_intent_envelope,
    validate_agent_response,
)
from intentusnet.protocol.errors import EMCLValidationError

from intentusnet.security.emcl.aes_gcm import AESGCMEMCLProvider
from intentusnet.security.emcl.simple_hmac import SimpleHMACEMCLProvider
from intentusnet.security.emcl.base import EMCLProvider


# ----------------------------------------------------------------------
# Import agents
# ----------------------------------------------------------------------
from .agents.nlu_agent import NLUAgent
from .agents.web_search_agent import WebSearchAgent
from .agents.alt_search_agent import AltSearchAgent
from .agents.scraper_agent import ScraperAgent
from .agents.cleaner_agent import CleanerAgent
from .agents.summarizer_agent import SummarizerAgent
from .agents.reasoning_agent import ReasoningAgent
from .agents.action_agent import ActionAgent
from .agents.research_orchestrator import ResearchOrchestratorAgent


app = FastAPI(title="IntentusNet HTTP Gateway", version="1.0")


# ----------------------------------------------------------------------
# EMCL Config
# ----------------------------------------------------------------------
EMCL_ENABLED = os.getenv("INTENTUSNET_EMCL_ENABLED", "false").lower() == "true"
EMCL_MODE = os.getenv("INTENTUSNET_EMCL_MODE", "aes-gcm").lower()
EMCL_KEY = os.getenv("INTENTUSNET_EMCL_KEY", "")

emcl_provider: EMCLProvider | None = None

if EMCL_ENABLED:
    if not EMCL_KEY:
        raise RuntimeError("EMCL enabled but INTENTUSNET_EMCL_KEY empty")

    if EMCL_MODE == "aes-gcm":
        emcl_provider = AESGCMEMCLProvider(EMCL_KEY)
    elif EMCL_MODE == "simple-hmac":
        emcl_provider = SimpleHMACEMCLProvider(EMCL_KEY)
    else:
        raise RuntimeError(f"Unknown EMCL mode '{EMCL_MODE}'")


# ----------------------------------------------------------------------
# Build runtime (local orchestrator)
# ----------------------------------------------------------------------
runtime = IntentusRuntime()

runtime.register_agent(lambda r: NLUAgent(r))
runtime.register_agent(lambda r: WebSearchAgent(r))
runtime.register_agent(lambda r: AltSearchAgent(r))
runtime.register_agent(lambda r: ScraperAgent(r))
runtime.register_agent(lambda r: CleanerAgent(r))
runtime.register_agent(lambda r: SummarizerAgent(r))
runtime.register_agent(lambda r: ReasoningAgent(r))
runtime.register_agent(lambda r: ActionAgent(r))
runtime.register_agent(lambda r: ResearchOrchestratorAgent(r))


# ----------------------------------------------------------------------
# Helper: Convert dict → IntentEnvelope
# ----------------------------------------------------------------------
def build_intent_envelope(data: dict) -> IntentEnvelope:
    validate_intent_envelope(data)

    return IntentEnvelope(
        version=data["version"],
        intent=IntentRef(**data["intent"]),
        payload=data["payload"],
        context=IntentContext(**data["context"]),
        metadata=IntentMetadata(**data["metadata"]),
        routing=RoutingOptions(**data["routing"]),
        routingMetadata=RoutingMetadata(**data["routingMetadata"]),
    )


# ----------------------------------------------------------------------
# Gateway entry: POST /intent
# ----------------------------------------------------------------------
@app.post("/intent")
async def handle_intent(request: Request):
    """
    Accepts Intentus Transport Envelopes:

    PLAIN:
        {
          "messageType": "intent",
          "body": { ...IntentEnvelope... }
        }

    EMCL:
        {
          "messageType": "emcl",
          "body": { ...EMCLEnvelope... }
        }

    Returns:
        Always a TransportEnvelope with `messageType` = "response" or "emcl".
    """

    try:
        frame = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    msg_type = frame.get("messageType")
    body = frame.get("body") or {}

    # ================================================================
    # Case 1: EMCL message
    # ================================================================
    if msg_type == "emcl":
        if not emcl_provider:
            raise HTTPException(status_code=400, detail="Gateway not configured for EMCL")

        try:
            envelope = EMCLEnvelope(**body)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid EMCL envelope: {e}")

        try:
            inner = emcl_provider.decrypt(envelope)
        except EMCLValidationError as e:
            raise HTTPException(status_code=400, detail=str(e))

        env = build_intent_envelope(inner)

        # Route request
        result: AgentResponse = runtime.router.route_intent(env)

        # Validate outgoing response
        result_dict = {
            "version": result.version,
            "status": result.status,
            "payload": result.payload,
            "metadata": result.metadata,
            "error": result.error.__dict__ if result.error else None,
        }
        validate_agent_response(result_dict)

        # Encrypt response
        encrypted_out = emcl_provider.encrypt(result_dict)

        return JSONResponse({
            "messageType": "emcl",
            "protocol": "INTENTUSNET/1.0",
            "body": encrypted_out.__dict__,
        })

    # ================================================================
    # Case 2: PLAINTEXT INTENT
    # ================================================================
    elif msg_type == "intent":
        inner = body
        env = build_intent_envelope(inner)

        result: AgentResponse = runtime.router.route_intent(env)

        result_dict = {
            "version": result.version,
            "status": result.status,
            "payload": result.payload,
            "metadata": result.metadata,
            "error": result.error.__dict__ if result.error else None,
        }

        validate_agent_response(result_dict)

        return JSONResponse({
            "messageType": "response",
            "protocol": "INTENTUSNET/1.0",
            "body": result_dict,
        })

    # ================================================================
    # Unknown type
    # ================================================================
    else:
        raise HTTPException(status_code=400, detail=f"Unknown messageType '{msg_type}'")
