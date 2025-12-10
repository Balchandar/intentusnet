from __future__ import annotations
from typing import Dict, List, Optional, TYPE_CHECKING
import time
import uuid

from intentusnet.protocol.models import (
    IntentEnvelope,
    AgentResponse,
    ErrorInfo,
    ErrorCode,
    RoutingMetadata,
)
from intentusnet.protocol.enums import RoutingStrategy
from intentusnet.core.registry import AgentRegistry
from intentusnet.core.tracing import IntentusNetTracer

# Optional EMCL imports (safe)
try:
    from intentusnet.security.emcl import extend_identity_chain
except Exception:
    def extend_identity_chain(chain, ident=None):
        return chain

if TYPE_CHECKING:
    from intentusnet.security.emcl import EMCLProvider


class RouterDecision:
    def __init__(
        self,
        selected: Optional[str],
        candidates: List[str],
        strategy: RoutingStrategy,
        error: Optional[ErrorInfo]
    ):
        self.selectedAgent = selected
        self.candidates = candidates
        self.strategy = strategy
        self.error = error


class IntentRouter:

    def __init__(
        self,
        registry: AgentRegistry,
        tracer: IntentusNetTracer,
        emcl_provider: "EMCLProvider | None" = None,
    ):
        self._registry = registry
        self._tracer = tracer
        self._emcl = emcl_provider  # OPTIONAL EMCL provider

    # ----------------------------------------------------------------------
    def _now_iso(self):
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # ----------------------------------------------------------------------
    # Optional: EMCL Decryption
    def _decrypt_if_needed(self, env: IntentEnvelope):
        if not self._emcl:
            return

        if not isinstance(env.payload, dict):
            return

        if "__emcl__" not in env.payload:
            return

        try:
            decrypted = self._emcl.decrypt(env.payload["__emcl__"])
            env.payload = decrypted
            env.metadata.identityChain = extend_identity_chain(
                env.metadata.identityChain, "router:decrypt"
            )
        except Exception as ex:
            raise RuntimeError(f"EMCL decrypt failed: {ex}")

    # ----------------------------------------------------------------------
    # Optional: EMCL Encryption
    def _encrypt_if_needed(self, env: IntentEnvelope, resp: AgentResponse) -> AgentResponse:
        if not self._emcl:
            return resp

        # Do not encrypt errors
        if resp.error is not None:
            return resp

        encrypted = self._emcl.encrypt(
            resp.payload,
            identity_chain=extend_identity_chain(env.metadata.identityChain, "router:encrypt")
        )

        resp.payload = {"__emcl__": encrypted}
        resp.metadata["emcl"] = True
        return resp

    # ----------------------------------------------------------------------
    def _select_agent(self, env: IntentEnvelope) -> RouterDecision:
        intent_name = env.intent.name

        # -------------------------
        # TARGET AGENT OVERRIDE
        # -------------------------
        if env.routing and env.routing.targetAgent:
            tgt = env.routing.targetAgent
            if tgt in self._registry.agents:
                return RouterDecision(
                    selected=tgt,
                    candidates=[tgt],
                    strategy=env.metadata.strategy,
                    error=None,
                )

        # -------------------------
        # FIND CANDIDATE AGENTS
        # -------------------------
        candidates = []
        priorities = {}

        for name, agent in self._registry.agents.items():
            if agent.supports_intent(intent_name):
                candidates.append(name)
                priorities[name] = agent.priority_for_intent(intent_name)

        if not candidates:
            err = ErrorInfo(
                code=ErrorCode.ROUTING_ERROR,
                message=f"No agent can handle intent '{intent_name}'",
            )
            return RouterDecision(None, [], env.metadata.strategy, err)

        # -------------------------
        # FALLBACK + PRIORITY MERGE
        # -------------------------
        explicit = []
        if env.routing and env.routing.fallbackAgents:
            for a in env.routing.fallbackAgents:
                if a in candidates:
                    explicit.append(a)

        priority_sorted = sorted(candidates, key=lambda x: priorities[x])
        merged = explicit + [a for a in priority_sorted if a not in explicit]

        return RouterDecision(
            selected=merged[0],
            candidates=merged,
            strategy=env.metadata.strategy,
            error=None,
        )

    # ----------------------------------------------------------------------
    def route(self, env: IntentEnvelope) -> AgentResponse:
        # STEP 0 — Optional EMCL decrypt
        try:
            self._decrypt_if_needed(env)
        except Exception as ex:
            return AgentResponse.failure(
                ErrorInfo(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=str(ex),
                    retryable=False,
                )
            )

        start = self._now_iso()
        decision = self._select_agent(env)

        # Build routing metadata
        env.routingMetadata = RoutingMetadata(
            selectedAgent=decision.selectedAgent,
            candidates=decision.candidates,
            strategy=decision.strategy.value,
            error=decision.error.message if decision.error else None,
        )

        # Routing error
        if decision.error:
            return AgentResponse.failure(decision.error)

        # Execute agent
        agent = self._registry.agents[decision.selectedAgent]
        res = agent.handle(env)

        # Tracing
        self._tracer.record(
            traceId=env.metadata.traceId,
            span={
                "id": str(uuid.uuid4()),
                "name": f"route:{env.intent.name}",
                "start": start,
                "end": self._now_iso(),
                "attributes": {
                    "agent": decision.selectedAgent,
                    "candidates": decision.candidates,
                    "error": bool(res.error),
                },
            },
        )

        # STEP 3 — Optional EMCL encrypt
        return self._encrypt_if_needed(env, res)
