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

logger = logging.getLogger("dlika.weather")

WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    80: "Rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


class WeatherAgent(BaseAgent):
    """
    Weather lookup using Open-Meteo.
    """

    API_URL = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude={lat}&longitude={lng}&current_weather=true"
    )

    def handle_intent(self, env) -> AgentResponse:
        action = env.payload.get("action")

        if action == "current_weather":
            return self._current_weather(env)

        return AgentResponse(
            version="1.0",
            status="error",
            payload={"error": "unknown_action"},
            metadata={"agent": self.definition.name},
        )

    def _current_weather(self, env) -> AgentResponse:
        p = env.payload
        lat = p["lat"]
        lng = p["lng"]

        url = self.API_URL.format(lat=lat, lng=lng)

        try:
            r = requests.get(url, timeout=8)
            r.raise_for_status()
            data = r.json()

            cw = data.get("current_weather")
            if not cw:
                raise RuntimeError("current_weather missing")

            code = int(cw.get("weathercode", -1))
            desc = WEATHER_CODES.get(code, "Unknown")

            result = {
                "temperature_c": cw.get("temperature"),
                "windspeed_kmh": cw.get("windspeed"),
                "weathercode": code,
                "description": desc,
                "raw": cw,
            }

            logger.info(
                "[WEATHER] %s, %.1f°C, wind=%.1f km/h",
                desc,
                cw.get("temperature"),
                cw.get("windspeed"),
            )

            return AgentResponse(
                version="1.0",
                status="success",
                payload=result,
                metadata={"agent": self.definition.name},
            )
        except Exception as ex:
            logger.warning("[WEATHER] Error: %s", ex)
            return AgentResponse(
                version="1.0",
                status="error",
                payload={"error": str(ex)},
                metadata={"agent": self.definition.name},
            )


def build_weather_definition() -> AgentDefinition:
    return AgentDefinition(
        name="dlika-weather",
        version="1.0",
        identity=AgentIdentity(agentId="dlika-weather", roles=["weather"]),
        capabilities=[
            Capability(
                intent=IntentRef(name="weather.lookup", version="1.0"),
                inputSchema={},
                outputSchema={},
            )
        ],
        endpoint=AgentEndpoint(type="local", address="inprocess://dlika-weather"),
        health=AgentHealth(status="healthy", lastHeartbeat=""),
        runtime=AgentRuntimeInfo(
            language="python",
            environment="local",
            scaling="manual",
        ),
    )
