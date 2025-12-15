from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, TYPE_CHECKING
import uuid
import datetime as dt

from intentusnet.utils.id_generator import generate_uuid
from intentusnet.utils.timestamps import now_iso

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

    # ==========================================================
    # Router-facing entrypoint
    # ==========================================================
    def handle(self, env: IntentEnvelope) -> AgentResponse:
        # Ensure traceId exists
        if not env.metadata.traceId:
            env.metadata.traceId = str(uuid.uuid4())

        # Track routing path (NOT metadata mutation)
        env.routingMetadata.decisionPath.append(self.definition.name)

        try:
            response = self.handle_intent(env)
        except Exception as ex:
            return AgentResponse.failure(
                self.error(str(ex)),
                agent=self.definition.name,
                trace_id=env.metadata.traceId,
            )

        response.metadata.setdefault("agent", self.definition.name)
        response.metadata.setdefault("traceId", env.metadata.traceId)
        response.metadata.setdefault("timestamp", now_iso())
        return response

    # ==========================================================
    # Agent business logic
    # ==========================================================
    @abstractmethod
    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        raise NotImplementedError

    # ==========================================================
    # Downstream intent emission
    # ==========================================================
    def emit_intent(
        self,
        intent_name: str,
        payload: Dict[str, Any],
        *,
        priority: Priority = Priority.NORMAL,
        tags: Optional[List[str]] = None,
        routing: Optional[RoutingOptions] = None,
    ) -> AgentResponse:

        now = now_iso()
        env = IntentEnvelope(
            version="1.0",
            intent=IntentRef(name=intent_name, version="1.0"),
            payload=payload,
            context=IntentContext(
                sourceAgent=self.definition.name,
                timestamp=now,
                priority=priority,
                tags=list(tags or []),
            ),
            metadata=IntentMetadata(
                requestId=str(generate_uuid()),
                source=self.definition.name,
                createdAt=now,
                traceId=str(generate_uuid()),
            ),
            routing=routing or RoutingOptions(),
            routingMetadata=RoutingMetadata(),
        )

        return self.router.route_intent(env)

    # ==========================================================
    # Error helper
    # ==========================================================
    def error(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.INTERNAL_AGENT_ERROR,
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ) -> ErrorInfo:
        return ErrorInfo(
            code=code,
            message=message,
            retryable=retryable,
            details=details or {},
        )
