from __future__ import annotations
from typing import Any, Dict, Optional
import uuid
import datetime as dt

from intentusnet.protocol.models import (
    IntentEnvelope,
    IntentRef,
    IntentContext,
    IntentMetadata,
    AgentResponse,
    ErrorInfo,
)
from intentusnet.protocol.enums import Priority, ErrorCode


class BaseAgent:
    """
    Base class for all IntentusNet agents.

    Responsibilities:
    - Provide definition (name, capabilities)
    - Implement handle()
    - Call other agents via emit_intent()
    - Standardized error creation (returns ErrorInfo)
    """

    def __init__(self, definition, router):
        self.definition = definition
        self.router = router

    # ---------------------------------------------------------
    # Main entrypoint called by Router
    # ---------------------------------------------------------
    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        """
        Router always calls this wrapper.
        Agents only implement handle().
        """
        return self.handle(env)

    # ---------------------------------------------------------
    # Must be overridden by agent implementations
    # ---------------------------------------------------------
    def handle(self, env: IntentEnvelope) -> AgentResponse:
        raise NotImplementedError(
            f"Agent {self.definition.name} did not implement handle()"
        )

    # ---------------------------------------------------------
    # Emit sub-intents (used inside orchestrators)
    # ---------------------------------------------------------
    def emit_intent(
        self,
        intent_name: str,
        payload: Dict[str, Any],
        *,
        priority: Priority = Priority.NORMAL,
        tags: Optional[list[str]] = None,
    ) -> AgentResponse:
        """
        Allows an agent to call another agent internally.
        """

        now = dt.datetime.utcnow().isoformat() + "Z"

        env = IntentEnvelope(
            version="1.0",
            intent=IntentRef(name=intent_name),
            payload=payload,
            context=IntentContext(
                sessionId=str(uuid.uuid4()),
                workflowId=str(uuid.uuid4()),
            ),
            metadata=IntentMetadata(
                timestamp=now,
                priority=priority,
                tags=tags or [],
            )
        )

        return self.router.route_intent(env)

    # ---------------------------------------------------------
    # Standardized error constructor for all agents
    # ---------------------------------------------------------
    def error(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.AGENT_ERROR,
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ) -> ErrorInfo:
        """
        Agents should call: AgentResponse.failure(self.error("msg"))
        """

        return ErrorInfo(
            code=code,
            message=message,
            retryable=retryable,
            details=details or {},
        )
