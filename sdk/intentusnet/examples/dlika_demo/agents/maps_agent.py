from __future__ import annotations
import logging
from typing import Any, Dict

import requests

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

logger = logging.getLogger("dlika.maps")


class MapsAgent(BaseAgent):
    """
    OSRM-based routing for DLika.

    action = "travel_time"
    payload:
      {
        "origin": {"lat": float, "lng": float},
        "destination": {"lat": float, "lng": float}
      }
    """

    OSRM_URL = (
        "https://router.project-osrm.org/route/v1/driving/"
        "{orig_lng},{orig_lat};{dest_lng},{dest_lat}?overview=false"
    )

    def handle_intent(self, env) -> AgentResponse:
        action = env.payload.get("action")

        if action == "travel_time":
            return self._travel_time(env)

        return AgentResponse(
            version="1.0",
            status="error",
            payload={"error": "unknown_action"},
            metadata={"agent": self.definition.name},
        )

    def _travel_time(self, env) -> AgentResponse:
        p = env.payload
        origin = p["origin"]
        dest = p["destination"]

        url = self.OSRM_URL.format(
            orig_lat=origin["lat"],
            orig_lng=origin["lng"],
            dest_lat=dest["lat"],
            dest_lng=dest["lng"],
        )

        try:
            r = requests.get(url, timeout=8)
            r.raise_for_status()
            data = r.json()

            routes = data.get("routes") or []
            if not routes:
                raise RuntimeError("No route found")

            route = routes[0]
            duration = float(route["duration"])       # seconds
            distance_km = float(route["distance"]) / 1000.0

            minutes = round(duration / 60.0, 1)
            distance_km = round(distance_km, 2)

            logger.info(
                "[MAPS] Travel time=%.1f min, distance=%.2f km",
                minutes,
                distance_km,
            )

            return AgentResponse(
                version="1.0",
                status="success",
                payload={
                    "duration_seconds": duration,
                    "duration_minutes": minutes,
                    "distance_km": distance_km,
                },
                metadata={"agent": self.definition.name},
            )
        except Exception as ex:
            logger.warning("[MAPS] Error: %s", ex)
            return AgentResponse(
                version="1.0",
                status="error",
                payload={"error": str(ex)},
                metadata={"agent": self.definition.name},
            )


def build_maps_definition() -> AgentDefinition:
    return AgentDefinition(
        name="dlika-maps",
        version="1.0",
        identity=AgentIdentity(agentId="dlika-maps", roles=["maps"]),
        capabilities=[
            Capability(
                intent=IntentRef(name="maps.travel", version="1.0"),
                inputSchema={},
                outputSchema={},
            )
        ],
        endpoint=AgentEndpoint(type="local", address="inprocess://dlika-maps"),
        health=AgentHealth(status="healthy", lastHeartbeat=""),
        runtime=AgentRuntimeInfo(
            language="python",
            environment="local",
            scaling="manual",
        ),
    )
