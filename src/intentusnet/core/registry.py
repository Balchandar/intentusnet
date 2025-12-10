from __future__ import annotations
from typing import Dict
from intentusnet.protocol.models import AgentDefinition
from intentusnet.agents.base import BaseAgent


class AgentRegistry:

    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}

    # ---------------------------------------------------------
    def register(self, agent: BaseAgent) -> None:
        name = agent.definition.name
        self.agents[name] = agent

    # ---------------------------------------------------------
    def get(self, name: str) -> BaseAgent:
        return self.agents[name]

    # ---------------------------------------------------------
    def list(self):
        return list(self.agents.keys())
