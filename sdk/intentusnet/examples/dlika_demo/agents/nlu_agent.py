from __future__ import annotations
import re
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

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

logger = logging.getLogger("dlika.nlu")


class DlikaNLUAgent(BaseAgent):

    def __init__(self, definition, router, emcl=None, config_path=None) -> None:
        super().__init__(definition, router, emcl)

        # Load config
        default_path = Path(__file__).parent.parent / "dlika_config.json"
        config_path = config_path or default_path

        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        self.patterns = self.config["patterns"]
        self.location_map = self.config.get("locations", {})
        self.greetings = set(x.lower() for x in self.config.get("greetings", []))

    def handle_intent(self, env) -> AgentResponse:
        text = env.payload.get("text", "") or ""
        tl = text.lower()

        if tl in self.greetings:
            return AgentResponse(
                version=env.version,
                status="success",
                payload={
                    "task": "greeting"
                },
                metadata={"agent": self.definition.name},
            )

        task = "unknown"
        person = None
        phone = None
        location = None
        time_raw = None
        time_24h = None

        # ----------------------------------------
        # Phone extraction
        # ----------------------------------------
        m_phone = re.search(r"\b(\d{10})\b", tl)
        if m_phone:
            phone = m_phone.group(1)

        # ----------------------------------------
        # Time: HH:MM
        # ----------------------------------------
        m_hhmm = re.search(r"\b(\d{1,2}:\d{2})\b", tl)
        if m_hhmm:
            time_raw = m_hhmm.group(1)
            hh, mm = time_raw.split(":")
            time_24h = f"{int(hh):02d}:{int(mm):02d}"

        # ----------------------------------------
        # Time: AM/PM
        # ----------------------------------------
        m_ampm = re.search(r"\b(\d{1,2})\s*(am|pm)\b", tl)
        if m_ampm:
            hr = int(m_ampm.group(1))
            ap = m_ampm.group(2)
            if ap == "pm" and hr != 12:
                hr += 12
            if ap == "am" and hr == 12:
                hr = 0
            time_raw = m_ampm.group(0)
            time_24h = f"{hr:02d}:00"

        # ----------------------------------------
        # Person name after "meeting with"
        # ----------------------------------------
        m_person = re.search(r"meeting with ([A-Za-z ]+)", tl)
        if m_person:
            person = m_person.group(1).strip().title()

        # ----------------------------------------
        # Location (JSON mapping)
        # ----------------------------------------
        for key, value in self.location_map.items():
            if key in tl:
                location = value
                break

        # fallback
        if not location:
            m_loc = re.search(r"go to ([A-Za-z ]+)", tl)
            if m_loc:
                location = m_loc.group(1).strip().title()

        # ----------------------------------------
        # TASK CLASSIFICATION
        # ----------------------------------------

        def match_any(pattern_list):
            return any(p in tl for p in pattern_list)

        if match_any(self.patterns["confirm_cancel"]):
            task = "confirm_cancel"

        elif match_any(self.patterns["meeting"]):
            task = "schedule_meeting"

        elif match_any(self.patterns["save_contact"]) or (phone and "save" in tl):
            task = "save_contact"

        elif match_any(self.patterns["outing"]):
            task = "plan_outing"

        elif match_any(self.patterns["query_calendar"]):
            task = "query_calendar"

        logger.info(
            "[NLU] task=%s person=%s phone=%s time=%s location=%s",
            task, person, phone, time_24h, location
        )

        return AgentResponse(
            version=env.version,
            status="success",
            payload={
                "task": task,
                "person_name": person,
                "phone": phone,
                "location": location,
                "time_raw": time_raw,
                "time_24h": time_24h,
                "raw_text": text,
            },
            metadata={"agent": self.definition.name},
        )


def build_dlika_nlu_definition() -> AgentDefinition:
    return AgentDefinition(
        name="dlika-nlu",
        version="1.0",
        identity=AgentIdentity(agentId="dlika-nlu", roles=["nlu"]),
        capabilities=[
            Capability(
                intent=IntentRef(name="dlika.nlu", version="1.0"),
                inputSchema={},
                outputSchema={},
                examples=[]
            )
        ],
        endpoint=AgentEndpoint(type="local", address="inprocess://dlika-nlu"),
        health=AgentHealth(status="healthy", lastHeartbeat=""),
        runtime=AgentRuntimeInfo(language="python", environment="local", scaling="manual"),
    )
