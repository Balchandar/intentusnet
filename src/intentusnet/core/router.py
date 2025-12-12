from __future__ import annotations

from typing import Optional, List
import uuid
import datetime as dt
import logging
import concurrent.futures  # NEW: for PARALLEL strategy

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
    Core routing engine.

    Responsibilities:
      - Resolve intent → candidate agents via AgentRegistry
      - Apply routing strategy (DIRECT, FALLBACK, BROADCAST, PARALLEL)
      - Produce RouterDecision + TraceSpan
      - Call router middlewares (before_route, after_route, on_error)
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

    # -----------------------------------------------------------
    # Public API
    # -----------------------------------------------------------
    def route_intent(self, env: IntentEnvelope) -> AgentResponse:
        # Ensure traceId
        trace_id = getattr(env.metadata, "traceId", None) or uuid.uuid4().hex
        env.metadata.traceId = trace_id

        for m in self._middlewares:
            try:
                m.before_route(env)
            except Exception as ex:
                self._log.exception("Router middleware before_route failed: %s", ex)

        start = dt.datetime.utcnow()
        decision: Optional[RouterDecision] = None
        active_agent_name: str = "router"
        last_error: Optional[ErrorInfo] = None

        try:
            agents = self._registry.find_agents_for_intent(env.intent)

            if not agents:
                self._log.warning("No agents found for intent '%s'", env.intent.name)
                last_error = ErrorInfo(
                    code=ErrorCode.CAPABILITY_NOT_FOUND,
                    message=f"No agents registered for intent '{env.intent.name}'",
                    retryable=False,
                    details={},
                )
                raise RoutingError(last_error.message)

            # NEW: sort agents local-first, then by nodePriority
            agents = self._sort_agents_for_strategy(agents)

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
                # naive: send to all, return last success or first error if all fail
                response, active_agent_name, decision, last_error = self._route_broadcast(
                    env, agents, strategy
                )

            elif strategy == RoutingStrategy.PARALLEL:
                # NEW: real parallel strategy
                response, active_agent_name, decision, last_error = self._route_parallel(
                    env, agents, strategy
                )

            else:
                # Unknown strategies currently mapped to FALLBACK-like behavior
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

            span = self._make_span(
                env,
                agent_name=active_agent_name,
                decision=decision,
                start=start,
                success=False,
                error=last_error,
            )
            self._trace_sink.record(span)

            # Notify middlewares
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
                    "timestamp": self._now_iso(),
                    "traceId": trace_id,
                },
                error=last_error,
            )

        # Normal path
        success = not bool(response.error)

        span = self._make_span(
            env,
            agent_name=active_agent_name,
            decision=decision,
            start=start,
            success=success,
            error=response.error,
        )
        self._trace_sink.record(span)

        # Middlewares after success
        for m in self._middlewares:
            try:
                m.after_route(env, response)
            except Exception:
                self._log.exception("Router middleware after_route failed")

        # Also notify on_error if response contains error
        if response.error:
            for m in self._middlewares:
                try:
                    m.on_error(env, response.error)
                except Exception:
                    self._log.exception("Router middleware on_error failed")

        # Ensure metadata has traceId and agent
        response.metadata.setdefault("traceId", trace_id)
        response.metadata.setdefault("agent", active_agent_name)
        response.metadata.setdefault("timestamp", self._now_iso())

        return response

    # -----------------------------------------------------------
    # Sorting (local-first, nodePriority)
    # -----------------------------------------------------------
    def _sort_agents_for_strategy(self, agents: List) -> List:
        """
        Sort agents as:
          1. Local agents first (definition.nodeId is None)
          2. Then remote agents ordered by definition.nodePriority (lower first)
          3. Then by agent name as a tie-breaker

        This works for all strategies (DIRECT/FALLBACK/BROADCAST/PARALLEL).
        """

        def key(agent):
            d = agent.definition
            is_local = 0 if getattr(d, "nodeId", None) is None else 1
            # Fallback to 100 if nodePriority is missing
            node_priority = getattr(d, "nodePriority", 100)
            return (is_local, node_priority, d.name)

        return sorted(agents, key=key)

    # -----------------------------------------------------------
    # Strategy helpers
    # -----------------------------------------------------------
    def _select_direct_agent(self, env: IntentEnvelope, agents: List) -> "BaseAgent":
        """
        DIRECT strategy:
          - if routing.targetAgent set → direct match
          - else first agent (after sorting)
        """
        target = env.routing.targetAgent
        if target:
            for a in agents:
                if a.definition.name == target:
                    return a
            raise RoutingError(f"Target agent '{target}' not registered for intent '{env.intent.name}'")
        return agents[0]

    def _route_with_fallback(
        self,
        env: IntentEnvelope,
        agents: List,
        strategy: RoutingStrategy,
    ) -> tuple[AgentResponse, str, RouterDecision, Optional[ErrorInfo]]:
        last_error: Optional[ErrorInfo] = None

        for idx, agent in enumerate(agents):
            agent_name = agent.definition.name
            try:
                resp = agent.handle(env)
            except Exception as ex:
                logger.exception("Agent '%s' raised exception: %s", agent_name, ex)
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
            else:
                last_error = resp.error

        # all failed
        if last_error is None:
            last_error = ErrorInfo(
                code=ErrorCode.ROUTING_ERROR,
                message="All fallback agents failed without error info",
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
        agents: List,
        strategy: RoutingStrategy,
    ) -> tuple[AgentResponse, str, RouterDecision, Optional[ErrorInfo]]:
        last_error: Optional[ErrorInfo] = None
        last_success: Optional[AgentResponse] = None
        last_agent_name: str = "broadcast"

        for idx, agent in enumerate(agents):
            agent_name = agent.definition.name
            try:
                resp = agent.handle(env)
            except Exception as ex:
                logger.exception("Agent '%s' raised exception (broadcast): %s", agent_name, ex)
                last_error = ErrorInfo(
                    code=ErrorCode.INTERNAL_AGENT_ERROR,
                    message=str(ex),
                    retryable=False,
                    details={},
                )
                continue

            if resp.error is None:
                last_success = resp
                last_agent_name = agent_name

        if last_success:
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
        agents: List,
        strategy: RoutingStrategy,
    ) -> tuple[AgentResponse, str, RouterDecision, Optional[ErrorInfo]]:
        """
        Execute all agents concurrently and return the first successful response.

        If all fail, returns an error response summarizing the last error.
        """
        last_error: Optional[ErrorInfo] = None
        futures: dict[concurrent.futures.Future, Any] = {}

        # Simple per-call thread pool. If needed, can be promoted to a shared executor.
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(agents) or 1) as executor:
            for agent in agents:
                fut = executor.submit(agent.handle, env)
                futures[fut] = agent

            for fut in concurrent.futures.as_completed(futures):
                agent = futures[fut]
                agent_name = agent.definition.name
                try:
                    resp = fut.result()
                except Exception as ex:
                    logger.exception("Agent '%s' raised exception (parallel): %s", agent_name, ex)
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

        # No agent succeeded
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

    # -----------------------------------------------------------
    # Trace helpers
    # -----------------------------------------------------------
    def _make_decision(
        self,
        env: IntentEnvelope,
        agent_name: str,
        strategy: RoutingStrategy,
        success: bool,
        index: Optional[int],
    ) -> RouterDecision:
        return RouterDecision(
            traceId=env.metadata.traceId,
            intent=env.intent.name,
            chosenAgent=agent_name,
            strategy=strategy.value,
            success=success,
            index=index,
        )

    def _make_span(
        self,
        env: IntentEnvelope,
        agent_name: str,
        decision: Optional[RouterDecision],
        start: dt.datetime,
        success: bool,
        error: Optional[ErrorInfo],
    ) -> TraceSpan:
        end = dt.datetime.utcnow()
        return TraceSpan(
            traceId=env.metadata.traceId,
            agent=agent_name,
            intent=env.intent.name,
            startTime=start.isoformat() + "Z",
            endTime=end.isoformat() + "Z",
            latencyMs=int((end - start).total_seconds() * 1000),
            success=success,
            errorCode=error.code if error else None,
            errorMessage=error.message if error else None,
            routingDecision=decision,
        )

    @staticmethod
    def _now_iso() -> str:
        return dt.datetime.now(dt.timezone.utc).isoformat()
