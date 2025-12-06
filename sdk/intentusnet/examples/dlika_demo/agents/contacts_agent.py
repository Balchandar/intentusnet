from __future__ import annotations
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
from ..storage.contacts_db import SQLiteContactsDB

logger = logging.getLogger("dlika.contacts")


class ContactsAgent(BaseAgent):
    """
    Local contacts manager (SQLite) for DLika.
    """

    def __init__(self, definition, router, emcl=None, db_path: str = "dlika_contacts.db") -> None:
        super().__init__(definition, router, emcl)
        self.db = SQLiteContactsDB(db_path)

    def handle_intent(self, env) -> AgentResponse:
        payload = env.payload
        action = payload.get("action")

        if action == "save_contact":
            return self._save(env)
        if action == "get_contact":
            return self._get(env)
        if action == "list_contacts":
            return self._list(env)

        return AgentResponse(
            version="1.0",
            status="error",
            payload={"error": "unknown_action"},
            metadata={"agent": self.definition.name},
        )

    def _save(self, env) -> AgentResponse:
        name = env.payload["name"]
        phone = env.payload["phone"]
        metadata: Dict[str, Any] = env.payload.get("metadata", {})

        self.db.upsert_contact(name, phone, metadata)
        logger.info("[CONTACTS] Saved contact: %s → %s", name, phone)

        return AgentResponse(
            version="1.0",
            status="success",
            payload={"saved": True, "name": name, "phone": phone},
            metadata={"agent": self.definition.name},
        )

    def _get(self, env) -> AgentResponse:
        name = env.payload["name"]
        contact = self.db.get_contact(name)

        return AgentResponse(
            version="1.0",
            status="success",
            payload={"contact": contact},
            metadata={"agent": self.definition.name},
        )

    def _list(self, env) -> AgentResponse:
        contacts = self.db.list_contacts()
        return AgentResponse(
            version="1.0",
            status="success",
            payload={"contacts": contacts},
            metadata={"agent": self.definition.name},
        )


def build_contacts_definition() -> AgentDefinition:
    return AgentDefinition(
        name="dlika-contacts",
        version="1.0",
        identity=AgentIdentity(agentId="dlika-contacts", roles=["contacts"]),
        capabilities=[
            Capability(
                intent=IntentRef(name="contacts.manage", version="1.0"),
                inputSchema={},
                outputSchema={},
            )
        ],
        endpoint=AgentEndpoint(type="local", address="inprocess://dlika-contacts"),
        health=AgentHealth(status="healthy", lastHeartbeat=""),
        runtime=AgentRuntimeInfo(
            language="python",
            environment="local",
            scaling="manual",
        ),
    )
