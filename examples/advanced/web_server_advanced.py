"""
Advanced enterprise-grade IntentusNet HTTP Gateway

Features:
- EMCL encryption (AES-GCM / HMAC)
- JWT authentication (optional)
- Policy Engine (YAML/JSON)
- Rate limiting (per rule)
- Per-intent max timeout enforcement
- identityChain propagation on EMCL responses
- Router middleware-ready
- Centralized config (IntentusSettings)
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

# Settings
from intentusnet.core.settings import get_settings

# Runtime
from intentusnet.core.runtime import IntentusRuntime
from intentusnet.core.settings import get_settings
from intentusnet.core.middleware import LoggingRouterMiddleware, MetricsRouterMiddleware
from intentusnet.core.logging_config import configure_logging

# Protocol
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
from intentusnet.protocol.errors import EMCLValidationError, JWTAuthError

# Security
from intentusnet.security.emcl.aes_gcm import AESGCMEMCLProvider
from intentusnet.security.emcl.simple_hmac import SimpleHMACEMCLProvider
from intentusnet.security.emcl.identity_chain import extend_identity_chain

from intentusnet.security.jwt_auth import decode_jwt, IdentityContext
from intentusnet.security.policy_engine import EvaluationContext
from intentusnet.security.policy_loader import load_policy_engine_from_file
from intentusnet.security.rate_limiter import RateLimiter

# Demo agents
from .agents.nlu_agent import NLUAgent
from .agents.web_search_agent import WebSearchAgent
from .agents.alt_search_agent import AltSearchAgent
from .agents.scraper_agent import ScraperAgent
from .agents.cleaner_agent import CleanerAgent
from .agents.summarizer_agent import SummarizerAgent
from .agents.reasoning_agent import ReasoningAgent
from .agents.action_agent import ActionAgent
from .agents.research_orchestrator import ResearchOrchestratorAgent


# ================================================================
# Load settings
# ================================================================
settings = get_settings()
configure_logging()

app = FastAPI(
    title="IntentusNet Advanced Gateway",
    version="1.0",
    description="Enterprise security, policy, and EMCL support",
)

# ================================================================
# EMCL provider (optional)
# ================================================================
emcl_provider = None

if settings.emcl.enabled:
    mode = settings.emcl.mode.lower()
    key = settings.emcl.key

    if not key:
        raise RuntimeError("EMCL enabled but INTENTUSNET_EMCL_KEY not provided")

    if mode == "aes-gcm":
        emcl_provider = AESGCMEMCLProvider(key)
    elif mode == "simple-hmac":
        emcl_provider = SimpleHMACEMCLProvider(key)
    else:
        raise RuntimeError(f"Unknown EMCL mode '{mode}'")

# ================================================================
# Policy engine
# ================================================================
policy_engine = load_policy_engine_from_file(
    settings.policy.file,
    default_mode=settings.policy.default_mode,
)

rate_limiter = RateLimiter()

# ================================================================
# JWT Auth config
# ================================================================
jwt_cfg = settings.jwt

# ================================================================
# Runtime with middlewares
# ================================================================
runtime = IntentusRuntime(
    middlewares=[
        LoggingRouterMiddleware(),
        MetricsRouterMiddleware(),
        # You can add more middlewares here (Metrics, Tracing, etc.)
    ],
    emcl_provider=emcl_provider,
    # trace_sink uses default InMemory sink for now
)

# Register demo agents
runtime.register_agent(lambda r, e: NLUAgent(r))
runtime.register_agent(lambda r, e: WebSearchAgent(r))
runtime.register_agent(lambda r, e: AltSearchAgent(r))
runtime.register_agent(lambda r, e: ScraperAgent(r))
runtime.register_agent(lambda r, e: CleanerAgent(r))
runtime.register_agent(lambda r, e: SummarizerAgent(r))
runtime.register_agent(lambda r, e: ReasoningAgent(r))
runtime.register_agent(lambda r, e: ActionAgent(r))
runtime.register_agent(lambda r, e: ResearchOrchestratorAgent(r))

# ================================================================
# Threadpool for timeouts (configurable)
# ================================================================
executor = ThreadPoolExecutor(
    max_workers=settings.runtime.max_worker_threads
)

# ================================================================
# Helper functions
# ================================================================
def _extract_identity(request: Request) -> IdentityContext | None:
    if not jwt_cfg.enabled:
        return None

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = auth.removeprefix("Bearer ").strip()

    try:
        return decode_jwt(
            token,
            secret=jwt_cfg.secret,
            algorithms=[jwt_cfg.algorithm],
            issuer=jwt_cfg.issuer,
            audience=jwt_cfg.audience,
        )
    except JWTAuthError as ex:
        raise HTTPException(status_code=401, detail=str(ex))


def build_intent_envelope(data: dict, identity: IdentityContext | None) -> IntentEnvelope:
    validate_intent_envelope(data)

    ctx = dict(data["context"])
    meta = dict(data["metadata"])

    # enrich identity
    if identity:
        tags = list(ctx.get("tags") or [])
        tags.append(f"user:{identity.subject}")
        if identity.tenant:
            tags.append(f"tenant:{identity.tenant}")
        ctx["tags"] = tags

        meta.setdefault("caller", {})
        meta["caller"]["sub"] = identity.subject
        if identity.tenant:
            meta["caller"]["tenant"] = identity.tenant
        if identity.roles:
            meta["caller"]["roles"] = identity.roles

    return IntentEnvelope(
        version=data["version"],
        intent=IntentRef(**data["intent"]),
        payload=data["payload"],
        context=IntentContext(**ctx),
        metadata=IntentMetadata(**meta),
        routing=RoutingOptions(**data["routing"]),
        routingMetadata=RoutingMetadata(**data["routingMetadata"]),
    )


def _response_to_dict(resp: AgentResponse) -> dict:
    return {
        "version": resp.version,
        "status": resp.status,
        "payload": resp.payload,
        "metadata": resp.metadata,
        "error": resp.error.__dict__ if resp.error else None,
    }


def _evaluate_policy(env: IntentEnvelope, identity: IdentityContext | None):
    roles = identity.roles if identity else []
    tenant = identity.tenant if identity else None
    subject = identity.subject if identity else None

    ctx = EvaluationContext(
        subject=subject,
        roles=roles,
        tenant=tenant,
        intent=env.intent.name,
        agent=env.routing.targetAgent,
        payload=env.payload,
        metadata=env.metadata.__dict__,
        tags=getattr(env.context, "tags", []),
    )

    decision = policy_engine.evaluate(ctx)

    if not decision.allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Policy denied: {decision.reason}",
        )

    # Rate limiting
    if decision.rate_limit_key and decision.rate_limit_per_minute:
        allowed = rate_limiter.check_and_consume(
            decision.rate_limit_key,
            decision.rate_limit_per_minute,
        )
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded ({decision.rate_limit_key})",
            )

    return decision.max_timeout_ms


def _route_with_optional_timeout(env: IntentEnvelope, timeout_ms: int | None) -> AgentResponse:
    if not timeout_ms:
        return runtime.router.route_intent(env)

    future = executor.submit(runtime.router.route_intent, env)

    try:
        return future.result(timeout=timeout_ms / 1000.0)
    except FuturesTimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Request exceeded max_timeout_ms policy limit",
        )


# ================================================================
# HTTP: POST /intent
# ================================================================
@app.post("/intent")
async def handle_intent(request: Request):
    try:
        frame = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    msg_type = frame.get("messageType")
    body = frame.get("body") or {}

    identity = _extract_identity(request)

    # ------------------------------------------------------------
    # EMCL (encrypted) flow
    # ------------------------------------------------------------
    if msg_type == "emcl":
        if not emcl_provider:
            raise HTTPException(status_code=400, detail="EMCL not enabled")

        try:
            incoming = EMCLEnvelope(**body)
        except Exception as ex:
            raise HTTPException(status_code=400, detail=f"Bad EMCL envelope: {ex}")

        try:
            decrypted = emcl_provider.decrypt(incoming)
        except EMCLValidationError as ex:
            raise HTTPException(status_code=400, detail=str(ex))

        env = build_intent_envelope(decrypted, identity)

        timeout_ms = _evaluate_policy(env, identity)

        response = _route_with_optional_timeout(env, timeout_ms)
        result_dict = _response_to_dict(response)
        validate_agent_response(result_dict)

        encrypted_out = emcl_provider.encrypt(result_dict)

        # identityChain enrichment
        chain = encrypted_out.identityChain
        if identity:
            chain = extend_identity_chain(chain, f"user:{identity.subject}")
            if identity.tenant:
                chain = extend_identity_chain(chain, f"tenant:{identity.tenant}")

        chain = extend_identity_chain(chain, "gw:intentusnet-http")
        encrypted_out.identityChain = chain

        return JSONResponse(
            {
                "messageType": "emcl",
                "protocol": "INTENTUSNET/1.0",
                "body": encrypted_out.__dict__,
            }
        )

    # ------------------------------------------------------------
    # Plaintext intent flow
    # ------------------------------------------------------------
    elif msg_type == "intent":
        env = build_intent_envelope(body, identity)

        timeout_ms = _evaluate_policy(env, identity)

        response = _route_with_optional_timeout(env, timeout_ms)
        result_dict = _response_to_dict(response)
        validate_agent_response(result_dict)

        return JSONResponse(
            {
                "messageType": "response",
                "protocol": "INTENTUSNET/1.0",
                "body": result_dict,
            }
        )

    else:
        raise HTTPException(status_code=400, detail=f"Unknown messageType '{msg_type}'")
