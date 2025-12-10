# intentusnet/core/agent.py

from __future__ import annotations
from typing import Any, Dict
from intentusnet.protocol.models import AgentResponse, ErrorInfo, ErrorCode


class BaseAgent:
    """
    Shared logic for all agents in IntentusNet.
    """

    def __init__(self, definition, router):
        self.definition = definition
        self.router = router
        self.name = definition.name

    # ------------------------------------------------------
    # Capability helpers
    # ------------------------------------------------------
    def supports_intent(self, intent_name: str) -> bool:
        for c in self.definition.capabilities:
            if intent_name in c.intents:
                return True
        return False

    def priority_for_intent(self, intent_name: str) -> int:
        for c in self.definition.capabilities:
            if intent_name in c.intents:
                return c.priority
        return 9999

    # ------------------------------------------------------
    # Emit intent to router → sub-workflow
    # ------------------------------------------------------
    def emit_intent(self, intent_name: str, payload: Dict[str, Any]):
        from intentusnet.protocol.models import IntentEnvelope, IntentRef, IntentMetadata
        from intentusnet.utils import new_id

        env = IntentEnvelope(
            intent=IntentRef(name=intent_name),
            payload=payload,
            metadata=IntentMetadata(
                traceId=new_id(),
                requestId=new_id(),
                identityChain=[self.name],
            )
        )

        return self.router.route(env)

    # ------------------------------------------------------
    # Success / Failure wrappers
    # ------------------------------------------------------
    def success(self, payload: Dict[str, Any]):
        return AgentResponse.success(payload)

    def error(self, msg: str):
        return AgentResponse.failure(
            ErrorInfo(
                code=ErrorCode.AGENT_ERROR,
                message=msg,
                retryable=False
            )
        )

    # ------------------------------------------------------
    # To be overridden by child agents
    # ------------------------------------------------------
    def handle(self, env):
        raise NotImplementedError
