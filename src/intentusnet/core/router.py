from __future__ import annotations

import concurrent.futures
import datetime as dt
import logging
from typing import Optional, List, Tuple, Any

from intentusnet.core.agent import BaseAgent
from intentusnet.utils.id_generator import generate_uuid_hex
from intentusnet.utils.timestamps import now_iso, now_utc

from ..protocol.intent import IntentEnvelope
from ..protocol.response import AgentResponse, ErrorInfo
from ..protocol.tracing import RouterDecision, TraceSpan
from ..protocol.enums import ErrorCode, RoutingStrategy
from ..protocol.errors import RoutingError

from .tracing import TraceSink, InMemoryTraceSink
from .registry import AgentRegistry
from .middleware import RouterMiddleware

from ..recording.models import ExecutionRecord
from ..recording.recorder import InMemoryExecutionRecorder
from ..recording.store import FileExecutionStore

# Phase I REGULATED: Compliance integration
from ..security.compliance import (
    ComplianceConfig,
    ComplianceValidator,
    ComplianceLevel,
    ComplianceError,
)


logger = logging.getLogger("intentusnet.router")


class IntentRouter:
    """
    Core routing engine (v1 sync).

    Recording rules:
    - Recording is passive and must NOT affect routing decisions.
    - Historical retrieval returns stored responses; no routing or model calls occur.

    Determinism guarantees (Phase I):
    - DIRECT, FALLBACK, BROADCAST: Deterministic agent selection given identical
      (intent, agent registry, configuration). Same input -> same selection.
    - PARALLEL: Explicitly NON-DETERMINISTIC. Winner depends on completion timing.
      Blocked when require_determinism=True (default).

    See: docs/phase-i-remediation-plan.md for claim boundaries.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        *,
        trace_sink: Optional[TraceSink] = None,
        middlewares: Optional[list[RouterMiddleware]] = None,
        record_store: Optional[FileExecutionStore] = None,
        require_determinism: bool = True,
        compliance: Optional[ComplianceConfig] = None,
        wal_signing_enabled: bool = False,
    ) -> None:
        """
        Initialize the intent router.

        Args:
            registry: Agent registry for agent lookup
            trace_sink: Optional trace sink for observability
            middlewares: Optional list of router middlewares
            record_store: Optional execution record store
            require_determinism: Whether to enforce deterministic routing (default True)
            compliance: Optional compliance configuration (Phase I REGULATED)
            wal_signing_enabled: Whether WAL signing is enabled (Phase I REGULATED)

        Raises:
            ComplianceError: If compliance requirements are not met
        """
        self._registry = registry
        self._trace_sink = trace_sink or InMemoryTraceSink()
        self._middlewares: list[RouterMiddleware] = list(middlewares or [])
        self._record_store = record_store
        self._require_determinism = require_determinism
        self._config_hash: Optional[str] = None
        self._log = logger
        self._compliance = compliance
        self._wal_signing_enabled = wal_signing_enabled

        # Phase I REGULATED: Validate compliance at startup
        if compliance is not None:
            self._validate_compliance(compliance, wal_signing_enabled)

        # Compute config hash at init for drift detection
        self._config_hash = self._compute_config_hash()

    def _validate_compliance(
        self,
        compliance: ComplianceConfig,
        wal_signing_enabled: bool,
    ) -> None:
        """
        Validate that router configuration meets compliance requirements.

        Phase I REGULATED mode requires:
        - Deterministic routing (require_determinism=True)
        - Signed WAL entries (wal_signing_enabled=True)

        Args:
            compliance: The compliance configuration
            wal_signing_enabled: Whether WAL signing is enabled

        Raises:
            ComplianceError: If compliance requirements are not met
        """
        validator = ComplianceValidator(compliance)

        # Check determinism requirement
        validator.validate_router_config(self._require_determinism)

        # Check WAL signing requirement
        validator.validate_wal_signing(wal_signing_enabled)

        # Log compliance level
        self._log.info(
            "Router initialized with %s compliance. "
            "require_determinism=%s, wal_signing=%s",
            compliance.level.value,
            self._require_determinism,
            wal_signing_enabled,
        )

    @property
    def compliance_level(self) -> Optional[ComplianceLevel]:
        """Get the compliance level of this router, or None if not configured."""
        return self._compliance.level if self._compliance else None

    # ===========================================================
    # Public API
    # ===========================================================
    def route_intent(self, env: IntentEnvelope) -> AgentResponse:
        """
        Main routing entry point.
        Intentionally synchronous for v1.
        """

        # ---- Ensure traceId exists ----
        trace_id = getattr(env.metadata, "traceId", None) or generate_uuid_hex()
        env.metadata.traceId = trace_id

        # ---- Ensure identityChain exists (agents/proxies append hops) ----
        if not hasattr(env.metadata, "identityChain") or env.metadata.identityChain is None:
            env.metadata.identityChain = []

        # ---- Execution Recording (optional) ----
        recorder: Optional[InMemoryExecutionRecorder] = None
        if self._record_store is not None:
            record = ExecutionRecord.new(
                execution_id=generate_uuid_hex(),
                created_utc_iso=now_iso(),
                env=env,
            )
            recorder = InMemoryExecutionRecorder(record)
            recorder.record_event("INTENT_RECEIVED", {
                "traceId": trace_id,
                "intent": env.intent.name,
                "config_hash": self._config_hash,  # Phase I: Store for drift detection
                "require_determinism": self._require_determinism,
            })

        # ---- Middleware: before_route ----
        for m in self._middlewares:
            try:
                m.before_route(env)
            except Exception as ex:
                self._log.exception("Router middleware before_route failed: %s", ex)

        start = now_utc()
        decision: Optional[RouterDecision] = None
        active_agent_name: str = "router"
        last_error: Optional[ErrorInfo] = None

        try:
            agents = self._registry.find_agents_for_intent(env.intent)

            if not agents:
                last_error = ErrorInfo(
                    code=ErrorCode.CAPABILITY_NOT_FOUND,
                    message=f"No agents registered for intent '{env.intent.name}'",
                    retryable=False,
                    details={},
                )
                raise RoutingError(last_error.message)

            # ---- Deterministic ordering (CRITICAL) ----
            agents = self._sort_agents_for_strategy(agents)

            # ---- Strategy resolution ----
            strategy = getattr(env.routing, "strategy", None) or RoutingStrategy.DIRECT

            # ---- PARALLEL determinism enforcement (Phase I remediation) ----
            # PARALLEL strategy is non-deterministic: winner depends on completion timing.
            # Block it when require_determinism=True to prevent false compliance claims.
            if strategy == RoutingStrategy.PARALLEL and self._require_determinism:
                last_error = ErrorInfo(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=(
                        "PARALLEL routing strategy is non-deterministic. "
                        "Winner selection depends on agent completion timing, not priority. "
                        "To use PARALLEL, initialize router with require_determinism=False. "
                        "This disqualifies the execution from determinism guarantees. "
                        "For deterministic multi-agent execution, use FALLBACK or BROADCAST."
                    ),
                    retryable=False,
                    details={
                        "strategy": "PARALLEL",
                        "require_determinism": True,
                        "remediation": "Use require_determinism=False or change strategy",
                    },
                )
                raise RoutingError(last_error.message)

            # Log warning for PARALLEL even when allowed
            if strategy == RoutingStrategy.PARALLEL:
                self._log.warning(
                    "PARALLEL strategy in use. Execution is NON-DETERMINISTIC. "
                    "Winner depends on completion timing. trace_id=%s",
                    trace_id,
                )

            if strategy == RoutingStrategy.DIRECT:
                agent = self._select_direct_agent(env, agents)
                active_agent_name = agent.definition.name

                if recorder:
                    recorder.record_event("AGENT_ATTEMPT_START", {"agent": active_agent_name, "strategy": "DIRECT"})

                response = agent.handle(env)

                if recorder:
                    recorder.record_event(
                        "AGENT_ATTEMPT_END",
                        {"agent": active_agent_name, "status": "ok" if response.error is None else "error"},
                    )

                decision = self._make_decision(env, active_agent_name, strategy, response.error is None, None)

            elif strategy == RoutingStrategy.FALLBACK:
                response, active_agent_name, decision, last_error = self._route_with_fallback(
                    env, agents, strategy, recorder
                )

            elif strategy == RoutingStrategy.BROADCAST:
                response, active_agent_name, decision, last_error = self._route_broadcast(
                    env, agents, strategy, recorder
                )

            elif strategy == RoutingStrategy.PARALLEL:
                response, active_agent_name, decision, last_error = self._route_parallel(
                    env, agents, strategy, recorder
                )

            else:
                # Safety net: unknown strategy behaves like fallback
                response, active_agent_name, decision, last_error = self._route_with_fallback(
                    env, agents, strategy, recorder
                )

            if recorder and decision is not None:
                # Do not assume RouterDecision schema. We store best-effort dict.
                recorder.record_router_decision(getattr(decision, "__dict__", {"decision": str(decision)}))

        except Exception as ex:
            self._log.exception("Routing failed: %s", ex)

            if last_error is None:
                last_error = ErrorInfo(
                    code=ErrorCode.ROUTING_ERROR,
                    message=str(ex),
                    retryable=False,
                    details={},
                )

            # ---- Trace (v1 minimal TraceSpan) ----
            span = self._make_span(
                env=env,
                agent_name=active_agent_name,
                start=start,
                success=False,
                error=last_error,
            )
            self._trace_sink.record(span)

            # ---- Middleware: on_error ----
            for m in self._middlewares:
                try:
                    m.on_error(env, last_error)
                except Exception:
                    self._log.exception("Router middleware on_error failed")

            error_resp = AgentResponse(
                version="1.0",
                status="error",
                payload=None,
                metadata={
                    "agent": active_agent_name,
                    "timestamp": now_iso(),
                    "traceId": trace_id,
                },
                error=last_error,
            )

            if recorder:
                recorder.record_final_response(getattr(error_resp, "__dict__", {"response": str(error_resp)}))
                self._record_store.save(recorder.get_record())

            return error_resp

        # ---- Normal path ----
        success = response.error is None

        span = self._make_span(
            env=env,
            agent_name=active_agent_name,
            start=start,
            success=success,
            error=response.error,
        )
        self._trace_sink.record(span)

        # ---- Middleware: after_route ----
        for m in self._middlewares:
            try:
                m.after_route(env, response)
            except Exception:
                self._log.exception("Router middleware after_route failed")

        # ---- Middleware: on_error (if response contains error) ----
        if response.error:
            for m in self._middlewares:
                try:
                    m.on_error(env, response.error)
                except Exception:
                    self._log.exception("Router middleware on_error failed")

        # Ensure response metadata
        response.metadata.setdefault("traceId", trace_id)
        response.metadata.setdefault("agent", active_agent_name)
        response.metadata.setdefault("timestamp", now_iso())

        # Save record (success path)
        if recorder:
            recorder.record_final_response(getattr(response, "__dict__", {"response": str(response)}))
            self._record_store.save(recorder.get_record())

        return response

    # ===========================================================
    # Configuration Hash (for drift detection)
    # ===========================================================
    def _compute_config_hash(self) -> str:
        """
        Compute deterministic hash of router configuration.

        Used for:
        - Recording in WAL for drift detection during replay-diff
        - Detecting when configuration changed between execution and analysis

        Includes:
        - Agent names and priorities (sorted for determinism)
        - Require determinism flag
        - Router version
        """
        import hashlib
        import json

        agent_configs = []
        for name, agent in sorted(self._registry._agents.items()):
            defn = agent.definition
            agent_configs.append({
                "name": defn.name,
                "priority": getattr(defn, "nodePriority", 100),
                "is_remote": bool(getattr(defn, "nodeId", None)),
            })

        config_data = {
            "agents": agent_configs,
            "require_determinism": self._require_determinism,
            "version": "1.0",
        }

        encoded = json.dumps(config_data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()

    # ===========================================================
    # Deterministic Sorting
    # ===========================================================
    def _sort_agents_for_strategy(self, agents: List[BaseAgent]) -> List[BaseAgent]:
        """
        Sort agents deterministically for routing.

        Order: (is_remote ASC, nodePriority ASC, name ASC)

        This ensures identical agent selection across:
        - Different process restarts
        - Different machines
        - Replay-diff comparisons

        CRITICAL: This sort MUST NOT depend on registration order, random values,
        or any non-deterministic source.
        """
        def key(agent: BaseAgent):
            d = agent.definition
            is_remote = 1 if getattr(d, "nodeId", None) else 0
            node_priority = getattr(d, "nodePriority", 100)
            return (is_remote, node_priority, d.name)

        return sorted(agents, key=key)

    # ===========================================================
    # Strategy Implementations
    # ===========================================================
    def _select_direct_agent(self, env: IntentEnvelope, agents: List[BaseAgent]) -> BaseAgent:
        target = getattr(env.routing, "targetAgent", None)
        if target:
            for a in agents:
                if a.definition.name == target:
                    return a
            raise RoutingError(
                f"Target agent '{target}' not registered for intent '{env.intent.name}'"
            )
        return agents[0]

    def _route_with_fallback(
        self,
        env: IntentEnvelope,
        agents: List[BaseAgent],
        strategy: RoutingStrategy,
        recorder: Optional[InMemoryExecutionRecorder],
    ) -> Tuple[AgentResponse, str, RouterDecision, Optional[ErrorInfo]]:
        last_error: Optional[ErrorInfo] = None

        for idx, agent in enumerate(agents):
            agent_name = agent.definition.name

            if recorder:
                recorder.record_event(
                    "AGENT_ATTEMPT_START",
                    {"agent": agent_name, "strategy": "FALLBACK", "index": idx},
                )

            try:
                resp = agent.handle(env)
            except Exception as ex:
                logger.exception("Agent '%s' crashed", agent_name)
                last_error = ErrorInfo(
                    code=ErrorCode.INTERNAL_AGENT_ERROR,
                    message=str(ex),
                    retryable=False,
                    details={},
                )
                if recorder:
                    recorder.record_event(
                        "AGENT_ATTEMPT_END",
                        {"agent": agent_name, "status": "error", "exception": str(ex)},
                    )
                # fallback continues
                if idx + 1 < len(agents) and recorder:
                    recorder.record_event(
                        "FALLBACK_TRIGGERED",
                        {"from": agent_name, "to": agents[idx + 1].definition.name},
                    )
                continue

            if recorder:
                recorder.record_event(
                    "AGENT_ATTEMPT_END",
                    {"agent": agent_name, "status": "ok" if resp.error is None else "error"},
                )

            if resp.error is None:
                decision = self._make_decision(env, agent_name, strategy, True, idx)
                return resp, agent_name, decision, last_error

            last_error = resp.error
            if idx + 1 < len(agents) and recorder:
                recorder.record_event(
                    "FALLBACK_TRIGGERED",
                    {"from": agent_name, "to": agents[idx + 1].definition.name},
                )

        if last_error is None:
            last_error = ErrorInfo(
                code=ErrorCode.ROUTING_ERROR,
                message="All fallback agents failed",
                retryable=False,
                details={},
            )

        decision = self._make_decision(env, "fallback", strategy, False, None)
        return (
            AgentResponse(version="1.0", status="error", payload=None, metadata={}, error=last_error),
            "fallback",
            decision,
            last_error,
        )

    def _route_broadcast(
        self,
        env: IntentEnvelope,
        agents: List[BaseAgent],
        strategy: RoutingStrategy,
        recorder: Optional[InMemoryExecutionRecorder],
    ) -> Tuple[AgentResponse, str, RouterDecision, Optional[ErrorInfo]]:
        last_error: Optional[ErrorInfo] = None
        last_success: Optional[AgentResponse] = None
        last_agent_name = "broadcast"

        for agent in agents:
            agent_name = agent.definition.name
            if recorder:
                recorder.record_event("AGENT_ATTEMPT_START", {"agent": agent_name, "strategy": "BROADCAST"})

            try:
                resp = agent.handle(env)
                if resp.error is None:
                    last_success = resp
                    last_agent_name = agent_name
                else:
                    last_error = resp.error
            except Exception as ex:
                last_error = ErrorInfo(
                    code=ErrorCode.INTERNAL_AGENT_ERROR,
                    message=str(ex),
                    retryable=False,
                    details={},
                )

            if recorder:
                recorder.record_event(
                    "AGENT_ATTEMPT_END",
                    {"agent": agent_name, "status": "ok" if (last_success is not None and last_agent_name == agent_name) else "error"},
                )

        if last_success is not None:
            decision = self._make_decision(env, last_agent_name, strategy, True, None)
            return last_success, last_agent_name, decision, last_error

        if last_error is None:
            last_error = ErrorInfo(
                code=ErrorCode.ROUTING_ERROR,
                message="All broadcast agents failed",
                retryable=False,
                details={},
            )

        decision = self._make_decision(env, "broadcast", strategy, False, None)
        return (
            AgentResponse(version="1.0", status="error", payload=None, metadata={}, error=last_error),
            "broadcast",
            decision,
            last_error,
        )

    def _route_parallel(
        self,
        env: IntentEnvelope,
        agents: List[BaseAgent],
        strategy: RoutingStrategy,
        recorder: Optional[InMemoryExecutionRecorder],
    ) -> Tuple[AgentResponse, str, RouterDecision, Optional[ErrorInfo]]:
        """
        Execute agents in parallel, return first success.

        WARNING: This strategy is EXPLICITLY NON-DETERMINISTIC.

        The winner depends on:
        - Thread scheduling by the OS
        - Agent execution latency
        - Network conditions (for remote agents)

        Same input MAY produce different winners across runs.

        This method should only be called when require_determinism=False.
        The caller (route_intent) enforces this check.

        Candidate list IS deterministic (same agents sorted the same way).
        Winner selection IS NOT deterministic.
        """
        last_error: Optional[ErrorInfo] = None

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(agents) or 1) as executor:
            futures = {executor.submit(agent.handle, env): agent for agent in agents}

            for fut in concurrent.futures.as_completed(futures):
                agent = futures[fut]
                agent_name = agent.definition.name

                if recorder:
                    recorder.record_event("AGENT_ATTEMPT_START", {"agent": agent_name, "strategy": "PARALLEL"})

                try:
                    resp = fut.result()
                except Exception as ex:
                    last_error = ErrorInfo(
                        code=ErrorCode.INTERNAL_AGENT_ERROR,
                        message=str(ex),
                        retryable=False,
                        details={},
                    )
                    if recorder:
                        recorder.record_event("AGENT_ATTEMPT_END", {"agent": agent_name, "status": "error", "exception": str(ex)})
                    continue

                if recorder:
                    recorder.record_event(
                        "AGENT_ATTEMPT_END",
                        {"agent": agent_name, "status": "ok" if resp.error is None else "error"},
                    )

                if resp.error is None:
                    decision = self._make_decision(env, agent_name, strategy, True, None)
                    return resp, agent_name, decision, last_error

                last_error = resp.error

        if last_error is None:
            last_error = ErrorInfo(
                code=ErrorCode.ROUTING_ERROR,
                message="All parallel agents failed",
                retryable=False,
                details={},
            )

        decision = self._make_decision(env, "parallel", strategy, False, None)
        return (
            AgentResponse(version="1.0", status="error", payload=None, metadata={}, error=last_error),
            "parallel",
            decision,
            last_error,
        )

    # ===========================================================
    # Decision + Tracing helpers
    # ===========================================================
    def _make_decision(
        self,
        env: IntentEnvelope,
        agent_name: str,
        strategy: RoutingStrategy,
        success: bool,
        index: Optional[int],
    ) -> RouterDecision:
        if success:
            if strategy == RoutingStrategy.DIRECT:
                reason = "direct match"
            elif strategy == RoutingStrategy.FALLBACK:
                reason = f"fallback success at index {index}"
            elif strategy == RoutingStrategy.BROADCAST:
                reason = "broadcast last success"
            elif strategy == RoutingStrategy.PARALLEL:
                reason = "parallel first success"
            else:
                reason = "success"
        else:
            reason = "routing failed"

        # Keep your RouterDecision schema unchanged (do NOT assume fields).
        # If protocol.tracing.RouterDecision differs, this remains your contract.
        return RouterDecision(
            agent=agent_name,
            intent=env.intent.name,
            reason=reason,
        )

    def _make_span(
        self,
        *,
        env: IntentEnvelope,
        agent_name: str,
        start: dt.datetime,
        success: bool,
        error: Optional[ErrorInfo],
    ) -> TraceSpan:
        end = now_utc()
        latency_ms = (end - start).total_seconds() * 1000

        return TraceSpan(
            agent=agent_name,
            intent=env.intent.name,
            status="ok" if success else "error",
            latencyMs=latency_ms,
            error=(error.message if error else None),
        )
