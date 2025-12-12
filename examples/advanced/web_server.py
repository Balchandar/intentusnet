from __future__ import annotations

from fastapi import FastAPI, HTTPException
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
from intentusnet.protocol.validators import (
    validate_intent_envelope,
    validate_agent_response
)

from .agents.nlu_agent import NLUAgent
from .agents.research_orchestrator import ResearchOrchestratorAgent
from .agents.web_search_agent import WebSearchAgent
from .agents.alt_search_agent import AltSearchAgent
from .agents.scraper_agent import ScraperAgent
from .agents.cleaner_agent import CleanerAgent
from .agents.summarizer_agent import SummarizerAgent
from .agents.reasoning_agent import ReasoningAgent
from .agents.action_agent import ActionAgent

import uuid
import datetime as dt


app = FastAPI(title="IntentusNet HTTP Gateway Demo")

# ----------------------------------------------------------------------
# Build runtime + agents
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
# Helper: convert dict to IntentEnvelope (validates first)
# ----------------------------------------------------------------------
def build_intent_envelope(data: dict) -> IntentEnvelope:
    """
    Validate JSON → build IntentEnvelope dataclass object.
    """

    # 1) Validate incoming data as schema-only
    validate_intent_envelope(data)

    # 2) Construct dataclass
    env = IntentEnvelope(
        version=data["version"],
        intent=IntentRef(**data["intent"]),
        payload=data["payload"],
        context=IntentContext(**data["context"]),
        metadata=IntentMetadata(**data["metadata"]),
        routing=RoutingOptions(**data["routing"]),
        routingMetadata=RoutingMetadata(**data["routingMetadata"]),
    )

    return env


# ----------------------------------------------------------------------
# POST /intent – main entry point
# ----------------------------------------------------------------------
@app.post("/intent")
async def handle_intent_request(body: dict):
    """
    HTTP gateway entry point:
    - Validate JSON schema
    - Construct IntentEnvelope
    - Execute router
    - Validate AgentResponse
    - Return JSON to client
    """

    try:
        env = build_intent_envelope(body)

        result: AgentResponse = runtime.router.route_intent(env)

        # Convert result dataclass → dict
        result_dict = {
            "version": result.version,
            "status": result.status,
            "payload": result.payload,
            "metadata": result.metadata,
            "error": result.error.__dict__ if result.error else None,
        }

        # Validate outgoing schema too
        validate_agent_response(result_dict)

        return JSONResponse(result_dict)

    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))
from __future__ import annotations

import os
import uuid
import datetime as dt

from fastapi import FastAPI, HTTPException
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

from intentusnet.security.emcl.base import EMCLProvider
from intentusnet.security.emcl.aes_gcm import AESGCMEMCLProvider
from intentusnet.security.emcl.simple_hmac import SimpleHMACEMCLProvider

from .agents.nlu_agent import NLUAgent
from .agents.research_orchestrator import ResearchOrchestratorAgent
from .agents.web_search_agent import WebSearchAgent
from .agents.alt_search_agent import AltSearchAgent
from .agents.scraper_agent import ScraperAgent
from .agents.cleaner_agent import CleanerAgent
from .agents.summarizer_agent import SummarizerAgent
from .agents.reasoning_agent import ReasoningAgent
from .agents.action_agent import ActionAgent


app = FastAPI(title="IntentusNet HTTP Gateway Demo")

# ----------------------------------------------------------------------
# Runtime + agents
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
# Helper: build IntentEnvelope from dict (with validation)
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
# POST /intent
# ----------------------------------------------------------------------
@app.post("/intent")
async def handle_intent_request(body: dict):
    """
    If EMCL is disabled:
        body = IntentEnvelope dict

    If EMCL is enabled:
        body = EMCLEnvelope dict, decrypted into IntentEnvelope dict.
    """
    try:
        inner = body

        # 2) Build IntentEnvelope from inner dict (with validation)
        env = build_intent_envelope(inner)

        # 3) Route
        result: AgentResponse = runtime.router.route_intent(env)

        # 4) Convert AgentResponse → dict
        result_dict = {
            "version": result.version,
            "status": result.status,
            "payload": result.payload,
            "metadata": result.metadata,
            "error": result.error.__dict__ if result.error else None,
        }

        # 5) Validate outgoing response
        validate_agent_response(result_dict)

        return JSONResponse(result_dict)

    except HTTPException:
        raise
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))
