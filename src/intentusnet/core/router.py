# intentusnet/core/router.py

from __future__ import annotations

import concurrent.futures
import datetime as dt
import logging
from typing import Optional, List, Tuple

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

logger = logging.getLogger("intentusnet.router")


class IntentRouter:
    """
    Core routing engine (v1 sync).

    Responsibilities:
      - Resolve intent → candidate agents via AgentRegistry
      - Apply routing strategy (DIRECT, FALLBACK, BROADCAST, PARALLEL)
      - Deterministic agent selection (local-first, nodePriority, name)
      - Call router middlewares (before_route, after_route, on_error)
      - Record TraceSpan into TraceSink
    """

    def __init__(
        self,
        registry: AgentRegistry,
        *,
        trace_sink: Optional[TraceSink] = None,
        middlewares: Optional[list[RouterMiddleware]] = None,
    ) -> None:
        self._registry = registry
        self._trace_sink = trace_sink or InMemoryTraceSink()
        self._middlewares: list[RouterMiddleware] = list(middlewares or [])
        self._log = logger

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
            strategy = env.routing.strategy or RoutingStrategy.DIRECT

            if strategy == RoutingStrategy.DIRECT:
                agent = self._select_direct_agent(env, agents)
                active_agent_name = agent.definition.name
                response = agent.handle(env)

                decision = self._make_decision(env, active_agent_name, strategy, True, None)

            elif strategy == RoutingStrategy.FALLBACK:
                response, active_agent_name, decision, last_error = self._route_with_fallback(
                    env, agents, strategy
                )

            elif strategy == RoutingStrategy.BROADCAST:
                response, active_agent_name, decision, last_error = self._route_broadcast(
                    env, agents, strategy
                )

            elif strategy == RoutingStrategy.PARALLEL:
                response, active_agent_name, decision, last_error = self._route_parallel(
                    env, agents, strategy
                )

            else:
                # Safety net: unknown strategy behaves like fallback
                response, active_agent_name, decision, last_error = self._route_with_fallback(
                    env, agents, strategy
                )

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

            return AgentResponse(
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

        # Optional: decision can be attached for debugging without freezing schema
        # response.metadata.setdefault("routingDecision", decision.__dict__ if decision else None)

        return response

    # ===========================================================
    # Deterministic Sorting
    # ===========================================================
    def _sort_agents_for_strategy(self, agents: List[BaseAgent]) -> List[BaseAgent]:
        """
        Deterministic agent ordering:
          1. Local agents first (nodeId is None)
          2. Then by nodePriority (lower = higher priority)
          3. Then by agent name (stable tie-breaker)
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
        """
        DIRECT strategy:
          - routing.targetAgent wins if provided
          - otherwise first agent after deterministic sorting
        """
        target = env.routing.targetAgent
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
    ) -> Tuple[AgentResponse, str, RouterDecision, Optional[ErrorInfo]]:
        """
        FALLBACK:
          - Try agents sequentially
          - First success wins
        """
        last_error: Optional[ErrorInfo] = None

        for idx, agent in enumerate(agents):
            agent_name = agent.definition.name
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
                continue

            if resp.error is None:
                decision = self._make_decision(env, agent_name, strategy, True, idx)
                return resp, agent_name, decision, last_error

            last_error = resp.error

        if last_error is None:
            last_error = ErrorInfo(
                code=ErrorCode.ROUTING_ERROR,
                message="All fallback agents failed",
                retryable=False,
                details={},
            )

        decision = self._make_decision(env, "fallback", strategy, False, None)
        return (
            AgentResponse(
                version="1.0",
                status="error",
                payload=None,
                metadata={},
                error=last_error,
            ),
            "fallback",
            decision,
            last_error,
        )

    def _route_broadcast(
        self,
        env: IntentEnvelope,
        agents: List[BaseAgent],
        strategy: RoutingStrategy,
    ) -> Tuple[AgentResponse, str, RouterDecision, Optional[ErrorInfo]]:
        """
        BROADCAST:
          - Execute all agents sequentially
          - Return last success if any
          - If none succeed, return last error
        """
        last_error: Optional[ErrorInfo] = None
        last_success: Optional[AgentResponse] = None
        last_agent_name = "broadcast"

        for agent in agents:
            try:
                resp = agent.handle(env)
                if resp.error is None:
                    last_success = resp
                    last_agent_name = agent.definition.name
                else:
                    last_error = resp.error
            except Exception as ex:
                last_error = ErrorInfo(
                    code=ErrorCode.INTERNAL_AGENT_ERROR,
                    message=str(ex),
                    retryable=False,
                    details={},
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
            AgentResponse(
                version="1.0",
                status="error",
                payload=None,
                metadata={},
                error=last_error,
            ),
            "broadcast",
            decision,
            last_error,
        )

    def _route_parallel(
        self,
        env: IntentEnvelope,
        agents: List[BaseAgent],
        strategy: RoutingStrategy,
    ) -> Tuple[AgentResponse, str, RouterDecision, Optional[ErrorInfo]]:
        """
        PARALLEL:
          - Execute all agents concurrently
          - First success wins
          - Remaining completions are ignored (v1)
        """
        last_error: Optional[ErrorInfo] = None

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(agents) or 1) as executor:
            futures = {executor.submit(agent.handle, env): agent for agent in agents}

            for fut in concurrent.futures.as_completed(futures):
                agent = futures[fut]
                agent_name = agent.definition.name

                try:
                    resp = fut.result()
                except Exception as ex:
                    last_error = ErrorInfo(
                        code=ErrorCode.INTERNAL_AGENT_ERROR,
                        message=str(ex),
                        retryable=False,
                        details={},
                    )
                    continue

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
            AgentResponse(
                version="1.0",
                status="error",
                payload=None,
                metadata={},
                error=last_error,
            ),
            "parallel",
            decision,
            last_error,
        )

    # ===========================================================
    # Tracing helpers (v1 minimal TraceSpan)
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
        """
        v1 TraceSpan is intentionally minimal and MUST match protocol.tracing.TraceSpan.

        Expected TraceSpan fields (v1):
          - agent
          - intent
          - status ("ok" | "error")
          - latencyMs
          - error (optional str)
          - timestamp (default)
        """
        end = now_utc()
        latency_ms = (end - start).total_seconds() * 1000

        return TraceSpan(
            agent=agent_name,
            intent=env.intent.name,
            status="ok" if success else "error",
            latencyMs=latency_ms,
            error=(error.message if error else None),
        )
