from __future__ import annotations
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging
import time

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
from intentusnet.examples.dlika_demo.config import HOME_COORDS, DESTINATIONS

logger = logging.getLogger("dlika.planner")
THINK_DELAY = 0.4  # small delay to feel more "alive"


class DlikaPlannerAgent(BaseAgent):
    """
    DLika Planner – multi-agent orchestrator.

    Uses:
      - dlika.nlu
      - calendar.manage
      - contacts.manage
      - maps.travel
      - weather.lookup
    """

    def __init__(self, definition, router, emcl=None) -> None:
        super().__init__(definition, router, emcl)
        # Agent-level memory, survives across turns even if context is new
        self._pending_cancel: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Top-level dispatcher
    # ------------------------------------------------------------------
    def handle_intent(self, env) -> AgentResponse:
        text = env.payload.get("text", "") or ""
        date = datetime.now().date().isoformat()

        logger.info("[PLANNER] Received: %s", text)

        # 1) NLU
        time.sleep(THINK_DELAY)
        
        nlu_resp = self.emit_intent("dlika.nlu", {"text": text}, context=env.context)
        if nlu_resp.status != "success" or not nlu_resp.payload:
            return AgentResponse(
                version=env.version,
                status="error",
                payload={"message": "Sorry Boss, I couldn't understand that."},
                metadata={"agent": self.definition.name},
            )

        nlu = nlu_resp.payload
        task = nlu.get("task")
        
        logger.info("[PLANNER] Task=%s", task)

        if task == "greeting":
            return AgentResponse(
                version=env.version,
                status="success",
                payload={"message": "I'm DLika, how can I help you boss?"},
                metadata={"agent": self.definition.name},
            )

        if task == "schedule_meeting":
            return self._handle_schedule_meeting(env, nlu, date)

        if task == "plan_outing":
            return self._handle_plan_outing(env, nlu, date)

        if task == "confirm_cancel":
            return self._handle_confirm_cancel(env, date)

        # simple fallback
        return AgentResponse(
            version=env.version,
            status="success",
            payload={"message": "Got it Boss 😄", "debug": {"nlu": nlu}},
            metadata={"agent": self.definition.name},
        )

    # ------------------------------------------------------------------
    # SCHEDULE MEETING
    # ------------------------------------------------------------------
    def _handle_schedule_meeting(self, env, nlu: Dict[str, Any], date: str) -> AgentResponse:
        person = nlu.get("person_name") or "Someone"
        phone = nlu.get("phone")
        time_24h = nlu.get("time_24h") or "08:30"

        logger.info("[PLANNER] schedule_meeting person=%s phone=%s time=%s", person, phone, time_24h)

        # Save contact if phone exists
        if phone:
            time.sleep(THINK_DELAY)
            self.emit_intent(
                "contacts.manage",
                {"action": "save_contact", "name": person, "phone": phone},
                context=env.context,
            )

        # Create calendar event (30 mins)
        start_iso, end_iso = _range(date, time_24h, 30)

        time.sleep(THINK_DELAY)
        cal_resp = self.emit_intent(
            "calendar.manage",
            {
                "action": "create_event",
                "title": f"Meeting with {person}",
                "start": start_iso,
                "end": end_iso,
                "metadata": {"type": "meeting", "person": person, "phone": phone},
            },
            context=env.context,
        )

        msg = f"Yeah sure Boss ✨\n\nMeeting set with **{person}** at **{time_24h}**."
        if phone:
            msg += f"\nI also saved the number **{phone}**."

        return AgentResponse(
            version=env.version,
            status="success",
            payload={"message": msg, "debug": {"nlu": nlu, "calendar": cal_resp.payload}},
            metadata={"agent": self.definition.name},
        )

    # ------------------------------------------------------------------
    # PLAN OUTING
    # ------------------------------------------------------------------
    def _handle_plan_outing(self, env, nlu: Dict[str, Any], date: str) -> AgentResponse:
        time_24h = nlu.get("time_24h") or "20:00"
        location = nlu.get("location") or "Phoenix Marketcity"
        location = location.strip()

        logger.info("[PLANNER] plan_outing time=%s location=%s date=%s", time_24h, location, date)

        # 1) Check conflicts in that 30-min window
        time.sleep(THINK_DELAY)
        conflict_resp = self.emit_intent(
            "calendar.manage",
            {"action": "check_conflict", "date": date, "time_24h": time_24h},
            context=env.context,
        )
        conflict = conflict_resp.payload or {}
        print("[DEBUG PLANNER] conflict:", conflict)

        if conflict.get("conflict"):
            ev = conflict["events"][0]
            existing_title = ev.get("title", "another event")
            existing_start = ev.get("start", "")
            existing_time = existing_start[11:16] if len(existing_start) >= 16 else existing_start

            # store pending cancel state
            self._pending_cancel = {
                "event_id": ev["id"],
                "time_24h": time_24h,
                "location": location,
                "date": date,
            }
            print("[DEBUG STORE PENDING_CANCEL]", self._pending_cancel)

            msg = (
                f"Yeah sure Boss, but you already have **{existing_title}** at **{existing_time}**.\n"
                f"Shall I cancel it and block **{time_24h}** for **{location}**?"
            )

            return AgentResponse(
                version=env.version,
                status="success",
                payload={"message": msg, "debug": {"conflict": conflict}},
                metadata={"agent": self.definition.name},
            )

        # 2) No conflict → directly finalize outing
        return self._finalize_outing(env, time_24h, location, date, cancelled=False)

    # ------------------------------------------------------------------
    # CONFIRM CANCEL
    # ------------------------------------------------------------------
    def _handle_confirm_cancel(self, env, fallback_date: str) -> AgentResponse:
        print("[DEBUG LOAD PENDING_CANCEL]", self._pending_cancel)

        if not self._pending_cancel:
            return AgentResponse(
                version=env.version,
                status="success",
                payload={"message": "There is nothing to cancel Boss 😅"},
                metadata={"agent": self.definition.name},
            )

        pd = self._pending_cancel
        self._pending_cancel = None  # clear memory

        event_id = pd["event_id"]
        time_24h = pd["time_24h"]
        location = pd["location"]
        date = pd.get("date", fallback_date)

        logger.info(
            "[PLANNER] confirm_cancel event_id=%s time=%s location=%s date=%s",
            event_id, time_24h, location, date,
        )

        # 1) Cancel the existing event
        time.sleep(THINK_DELAY)
        cancel_resp = self.emit_intent(
            "calendar.manage",
            {"action": "cancel_event", "event_id": event_id},
            context=env.context,
        )
        print("[DEBUG CANCEL RESP]", cancel_resp.payload)

        # 2) Then finalize outing
        return self._finalize_outing(env, time_24h, location, date, cancelled=True)

    # ------------------------------------------------------------------
    # FINALIZE OUTING (MAPS + WEATHER + CALENDAR)
    # ------------------------------------------------------------------
    def _finalize_outing(
        self,
        env,
        time_24h: str,
        location: str,
        date: str,
        cancelled: bool,
    ) -> AgentResponse:
        dest = DESTINATIONS.get(location.lower(), HOME_COORDS)

        logger.info(
            "[PLANNER] finalize_outing time=%s location=%s date=%s cancelled=%s",
            time_24h, location, date, cancelled,
        )

        # Maps
        time.sleep(THINK_DELAY)
        maps_resp = self.emit_intent(
            "maps.travel",
            {
                "action": "travel_time",
                "origin": HOME_COORDS,
                "destination": dest,
            },
            context=env.context,
        )
        travel = maps_resp.payload or {}

        # Weather
        time.sleep(THINK_DELAY)
        weather_resp = self.emit_intent(
            "weather.lookup",
            {
                "action": "current_weather",
                "lat": dest["lat"],
                "lng": dest["lng"],
            },
            context=env.context,
        )
        weather = weather_resp.payload or {}

        # Block calendar 2 hours for outing
        start_iso, end_iso = _range(date, time_24h, 120)

        time.sleep(THINK_DELAY)
        outing_resp = self.emit_intent(
            "calendar.manage",
            {
                "action": "create_event",
                "title": f"Outing to {location}",
                "start": start_iso,
                "end": end_iso,
                "metadata": {"type": "outing", "cancelled_previous": cancelled},
            },
            context=env.context,
        )

        travel_min = travel.get("duration_minutes")
        distance_km = travel.get("distance_km")
        desc = weather.get("description")
        temp_c = weather.get("temperature_c")

        lines = ["Done Boss ✨", ""]
        if cancelled:
            lines.append("I cancelled your conflicting event and planned your outing.\n")

        lines.append(f"For **{location}** at **{time_24h}**:")

        if travel_min is not None and distance_km is not None:
            lines.append(f"- Travel time: around **{travel_min} minutes** (~{distance_km} km)")
        if temp_c is not None:
            lines.append(f"- Temperature: **{temp_c}°C**")
        if desc:
            lines.append(f"- Weather: **{desc}**")

        lines.append("")
        lines.append("I’ve blocked your calendar for the outing.")
        lines.append("Enjoy the small escape… you deserve it 💜")

        msg = "\n".join(lines)

        return AgentResponse(
            version=env.version,
            status="success",
            payload={
                "message": msg,
                "debug": {
                    "maps": travel,
                    "weather": weather,
                    "outing_event": outing_resp.payload,
                },
            },
            metadata={"agent": self.definition.name},
        )


def _range(date_str: str, time_24h: str, minutes: int):
    try:
        dt = datetime.fromisoformat(f"{date_str}T{time_24h}")
    except Exception:
        dt = datetime.now()
    end = dt + timedelta(minutes=minutes)
    return dt.isoformat(), end.isoformat()


def build_planner_definition() -> AgentDefinition:
    return AgentDefinition(
        name="dlika-planner",
        version="1.0",
        identity=AgentIdentity(agentId="dlika-planner", roles=["orchestrator"]),
        capabilities=[
            Capability(
                intent=IntentRef(name="dlika.handle_command", version="1.0"),
                inputSchema={},
                outputSchema={},
                examples=[],
                fallbackAgents=[],
                priority=0,
            )
        ],
        endpoint=AgentEndpoint(type="local", address="inprocess://dlika-planner"),
        health=AgentHealth(status="healthy", lastHeartbeat=""),
        runtime=AgentRuntimeInfo(
            language="python",
            environment="local",
            scaling="manual",
        ),
    )
