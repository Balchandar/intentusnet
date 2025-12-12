from __future__ import annotations

import uuid
import datetime as dt
from typing import Dict, Any, Optional, List

from intentusnet.protocol.enums import Priority
from intentusnet.protocol.intent import (
    IntentEnvelope,
    IntentRef,
    IntentContext,
    IntentMetadata,
    RoutingOptions,
    RoutingMetadata,
)


class IntentusClient:
    """
    The official public client API for IntentusNet.

    This class constructs IntentEnvelope objects and passes them
    to the runtime's configured transport.

    No backward compatibility is provided intentionally —
    this is the canonical interface for v0.1+.
    """

    def __init__(self, transport) -> None:
        self._transport = transport

    # ----------------------------------------------------------------------
    # Primary + Only Public API Method
    # ----------------------------------------------------------------------
    def send_intent(
        self,
        intent_name: str,
        payload: Dict[str, Any],
        *,
        priority: Priority = Priority.NORMAL,
        target_agent: Optional[str] = None,
        fallback_agents: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ):
        """
        Send an intent request to the Intentus runtime.

        Example:
            client.send_intent("SearchIntent", {"query": "python mcp"})
        """

        now = dt.datetime.utcnow().isoformat() + "Z"

        metadata = IntentMetadata(
            requestId=str(uuid.uuid4()),
            source="client",
            createdAt=now,
            traceId=str(uuid.uuid4()),
        )

        context = IntentContext(
            sourceAgent="client",
            timestamp=now,
            priority=priority,
            tags=tags or [],
        )

        routing = RoutingOptions(
            targetAgent=target_agent,
            fallbackAgents=fallback_agents or [],
        )

        envelope = IntentEnvelope(
            version="1.0",
            intent=IntentRef(name=intent_name, version="1.0"),
            payload=payload,
            context=context,
            metadata=metadata,
            routing=routing,
            routingMetadata=RoutingMetadata(),
        )

        return self._transport.send_intent(envelope)
