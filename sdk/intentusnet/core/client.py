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
from ..transport.base import Transport


class IntentusClient:
    """
    Public client for sending intents into the runtime.
    """

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def send(
        self,
        intent_name: str,
        payload: Dict[str, Any],
        *,
        session_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        priority: Priority = Priority.NORMAL,
        tags: Optional[List[str]] = None,
        target_agent: Optional[str] = None,
        fallback_agents: Optional[List[str]] = None,
    ):
        now = dt.datetime.utcnow().isoformat() + "Z"
        ctx = IntentContext(
            sessionId=session_id or str(uuid.uuid4()),
            workflowId=workflow_id or str(uuid.uuid4()),
        )
        meta = IntentMetadata(
            sourceAgent=None,
            timestamp=now,
            priority=priority,
            tags=tags or [],
        )
        routing = RoutingOptions(
            targetAgent=target_agent,
            fallbackAgents=fallback_agents or [],
        )
        env = IntentEnvelope(
            version="1.0",
            intent=IntentRef(name=intent_name, version="1.0"),
            payload=payload,
            context=ctx,
            metadata=meta,
            routing=routing,
            routingMetadata=RoutingMetadata(),
        )
        return self._transport.send_intent(env)
