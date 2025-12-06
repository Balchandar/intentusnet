from __future__ import annotations
from typing import Dict, Any, Optional, List
import uuid
import datetime as dt

from ..protocol.models import (
    IntentEnvelope,
    IntentRef,
    IntentContext,
    IntentMetadata,
    RoutingOptions,
    RoutingMetadata,
)
from ..protocol.enums import Priority


class BaseAgent:
    """
    Base class for all agents.
    - Override handle_intent()
    - Use emit_intent() to call other agents via the router.
    """

    def __init__(self, definition, router, emcl=None) -> None:
        self.definition = definition
        self.router = router
        self.emcl = emcl

    def handle_intent(self, env: IntentEnvelope):
        raise NotImplementedError

    def emit_intent(
        self,
        intent_name: str,
        payload: Dict[str, Any],
        context: Optional[IntentContext] = None,
        routing: Optional[RoutingOptions] = None,
        tags: Optional[List[str]] = None,
    ):
        now = dt.datetime.utcnow().isoformat() + "Z"
        ctx = context or IntentContext(
            sessionId=str(uuid.uuid4()),
            workflowId=str(uuid.uuid4()),
        )
        meta = IntentMetadata(
            sourceAgent=self.definition.name,
            timestamp=now,
            priority=Priority.NORMAL,
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
