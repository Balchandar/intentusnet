# FILE: src/intentusnet/core/client.py

from __future__ import annotations
from typing import Any, Dict
import uuid
import datetime as dt

from intentusnet.protocol.models import (
    IntentEnvelope,
    IntentRef,
    IntentMetadata,
    IntentContext,
    AgentResponse,
)
from intentusnet.protocol.enums import Priority


class IntentusClient:
    """
    High-level client for sending intents.
    Used by demos and applications.
    """

    def __init__(self, router):
        self._router = router
        self._session_id = str(uuid.uuid4())

    # ---------------------------------------------------------
    # User-facing API
    # ---------------------------------------------------------
    def send_intent(
        self,
        intent_name: str,
        payload: Dict[str, Any] | None = None,
        *,
        priority: Priority = Priority.NORMAL,
        tags: list[str] | None = None,
    ) -> AgentResponse:

        now = dt.datetime.now(dt.timezone.utc).isoformat() + "Z"

        env = IntentEnvelope(
            version="1.0",
            intent=IntentRef(name=intent_name),
            payload=payload or {},
            context=IntentContext(
                sessionId=self._session_id,
                workflowId=self._session_id,
            ),
            metadata=IntentMetadata(
                timestamp=now,
                priority=priority,
                tags=tags or [],
            ),
        )

        return self._router.send_intent(env)
