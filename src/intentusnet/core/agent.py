from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, TYPE_CHECKING
import uuid
import datetime as dt

from ..protocol import (
    IntentEnvelope,
    IntentRef,
    IntentContext,
    IntentMetadata,
    RoutingOptions,
    RoutingMetadata,
    AgentDefinition,
    AgentResponse,
    ErrorInfo,
)
from ..protocol.enums import Priority, ErrorCode

if TYPE_CHECKING:
    from .router import IntentRouter


class BaseAgent(ABC):
    """
    Base class for all Intentus agents.

    Responsibilities:
    - Hold its own AgentDefinition (identity, capabilities, runtime info)
    - Implement handle_intent() to process an IntentEnvelope
    - Provide emit_intent() helper to call other agents via the router
    - Provide error() helper to create structured ErrorInfo objects
    """

    def __init__(
        self,
        definition: AgentDefinition,
        router: "IntentRouter",
        emcl: Any = None,
    ) -> None:
        self.definition = definition
        self.router = router
        self.emcl = emcl

    # ------------------------------------------------------------------
    # Core contract
    # ------------------------------------------------------------------

    @abstractmethod
    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        """
        Process an incoming IntentEnvelope and return an AgentResponse.

        Concrete agents MUST implement this method.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Downstream intent emission (agent -> router -> other agents)
    # ------------------------------------------------------------------

    def emit_intent(
        self,
        intent_name: str,
        payload: Dict[str, Any],
        *,
        priority: Priority = Priority.NORMAL,
        tags: Optional[List[str]] = None,
        routing: Optional[RoutingOptions] = None,
    ) -> AgentResponse:
        """
        Emit a new intent to the router from within this agent.

        This is the standard way for orchestrator / composite agents
        to call downstream capabilities.
        """
        now = dt.datetime.utcnow().isoformat() + "Z"

        meta = IntentMetadata(
            requestId=str(uuid.uuid4()),
            source=self.definition.name,
            createdAt=now,
            traceId=str(uuid.uuid4()),
        )

        ctx = IntentContext(
            sourceAgent=self.definition.name,
            timestamp=now,
            priority=priority,
            tags=tags or [],
        )

        env = IntentEnvelope(
            version="1.0",
            intent=IntentRef(name=intent_name, version="1.0"),
            payload=payload,
            context=ctx,
            metadata=meta,
            routing=routing or RoutingOptions(),
            routingMetadata=RoutingMetadata(),
        )

        return self.router.route_intent(env)

    # ------------------------------------------------------------------
    # Error helper
    # ------------------------------------------------------------------

    def error(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.INTERNAL_AGENT_ERROR,
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ) -> ErrorInfo:
        """
        Convenience helper to construct a structured ErrorInfo.

        Typical usage in agents:

            if not topic:
                return AgentResponse.failure(
                    self.error("missing topic"),
                    agent=self.definition.name,
                    trace_id=env.metadata.traceId,
                )
        """
        return ErrorInfo(
            code=code,
            message=message,
            retryable=retryable,
            details=details or {},
        )
