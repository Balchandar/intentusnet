from __future__ import annotations

import uuid
import datetime as dt
from typing import Dict, Any, Optional, List

from intentusnet.protocol import (
    IntentEnvelope,
    IntentRef,
    IntentContext,
    IntentMetadata,
    RoutingOptions,
    RoutingMetadata,
    AgentResponse,
)
from intentusnet.protocol.enums import Priority
from intentusnet.utils.id_generator import generate_uuid
from intentusnet.utils.timestamps import now_iso


class IntentusClient:
    """
    Public client API for IntentusNet.

    This client is intentionally thin:
    - builds a valid IntentEnvelope
    - delegates execution to the configured transport
    """

    def __init__(self, transport) -> None:
        self._transport = transport

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def send_intent(
        self,
        intent_name: str,
        payload: Dict[str, Any],
        *,
        priority: Priority = Priority.NORMAL,
        target_agent: Optional[str] = None,
        fallback_agents: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> AgentResponse:
        """
        Send an intent request.

        Example:
            client.send_intent(
                "ResearchIntent",
                {"topic": "distributed systems"},
                priority=Priority.HIGH,
                tags=["demo"]
            )
        """

        now = now_iso()

        envelope = IntentEnvelope(
            version="1.0",
            intent=IntentRef(name=intent_name, version="1.0"),
            payload=payload,
            context=IntentContext(
                sourceAgent="client",
                timestamp=now,
                priority=priority,
                tags=list(tags or []),
            ),
            metadata=IntentMetadata(
                requestId=str(generate_uuid()),
                source="client",
                createdAt=now,
                traceId=str(generate_uuid()),
            ),
            routing=RoutingOptions(
                targetAgent=target_agent,
                fallbackAgents=list(fallback_agents or []),
            ),
            routingMetadata=RoutingMetadata(),
        )

        return self._transport.send_intent(envelope)
