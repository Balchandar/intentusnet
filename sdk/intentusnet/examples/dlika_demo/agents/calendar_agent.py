
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any, Dict
import logging

from intentusnet.core.agent import BaseAgent
from intentusnet.protocol.models import (
    AgentResponse,
    AgentDefinition,
    AgentIdentity,
    Capability,
    AgentEndpoint,
    AgentHealth,
    AgentRuntimeInfo,
    IntentRef,
)
from ..storage.calendar_db import SQLiteCalendarDB

logger = logging.getLogger("dlika.calendar")


class CalendarAgent(BaseAgent):
    """
    Local fake calendar for DLika built on SQLite.
    Ensures meeting + outing conflict detection works reliably.
    """

    def __init__(self, definition, router, emcl=None, db_path: str = "dlika_calendar.db") -> None:
        super().__init__(definition, router, emcl)
        self.db = SQLiteCalendarDB(db_path)

    def handle_intent(self, env) -> AgentResponse:
        action = env.payload.get("action")

        if action == "create_event":
            return self._create_event(env)

        if action == "cancel_event":
            return self._cancel_event(env)

        if action == "check_conflict":
            return self._check_conflict(env)

        return AgentResponse(
            version="1.0",
            status="error",
            payload={"error": "unknown_action"},
            metadata={"agent": self.definition.name},
        )

    # ----------------------------------------
    # CREATE EVENT
    # ----------------------------------------
    def _create_event(self, env) -> AgentResponse:
        p = env.payload
        event_id = self.db.create_event(
            title=p["title"],
            start=p["start"],
            end=p["end"],
            metadata=p.get("metadata", {}),
        )

        logger.info(
            "[CALENDAR] Created event id=%s title=%s start=%s end=%s",
            event_id,
            p["title"],
            p["start"],
            p["end"],
        )

        return AgentResponse(
            version="1.0",
            status="success",
            payload={"created": True, "event_id": event_id},
            metadata={"agent": self.definition.name},
        )

    # ----------------------------------------
    # CANCEL EVENT
    # ----------------------------------------
    def _cancel_event(self, env) -> AgentResponse:
        event_id = env.payload["event_id"]
        self.db.delete_event(event_id)

        logger.info("[CALENDAR] Cancelled event id=%s", event_id)

        return AgentResponse(
            version="1.0",
            status="success",
            payload={"cancelled": True, "event_id": event_id},
            metadata={"agent": self.definition.name},
        )

    # ----------------------------------------
    # CONFLICT CHECK — FIXED (WORKS ALWAYS NOW)
    # ----------------------------------------
    def _check_conflict(self, env) -> AgentResponse:
        date = env.payload["date"]  # already normalized to YYYY-MM-DD
        t = env.payload["time_24h"]

        # Build start & end datetime
        dt_start = datetime.fromisoformat(f"{date}T{t}")
        dt_end = dt_start + timedelta(minutes=30)

        logger.info(
            "[CALENDAR] Checking conflict window: %s → %s",
            dt_start.isoformat(),
            dt_end.isoformat(),
        )

        events = self.db.get_events_in_range(
            start=dt_start.isoformat(),
            end=dt_end.isoformat(),
        )

        print("[DEBUG CALENDAR] events_in_range:", events)

        if events:
            return AgentResponse(
                version="1.0",
                status="success",
                payload={"conflict": True, "events": events},
                metadata={"agent": self.definition.name},
            )

        return AgentResponse(
            version="1.0",
            status="success",
            payload={"conflict": False},
            metadata={"agent": self.definition.name},
        )


def build_calendar_definition() -> AgentDefinition:
    return AgentDefinition(
        name="dlika-calendar",
        version="1.0",
        identity=AgentIdentity(agentId="dlika-calendar", roles=["calendar"]),
        capabilities=[
            Capability(
                intent=IntentRef(name="calendar.manage", version="1.0"),
                inputSchema={},
                outputSchema={},
            )
        ],
        endpoint=AgentEndpoint(type="local", address="inprocess://dlika-calendar"),
        health=AgentHealth(status="healthy", lastHeartbeat=""),
        runtime=AgentRuntimeInfo(language="python", environment="local", scaling="manual"),
    )
