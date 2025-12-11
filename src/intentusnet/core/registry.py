from typing import List
from ..protocol.models import IntentRef
from ..agents.base import BaseAgent


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        name = agent.definition.name
        if name in self._agents:
            raise ValueError(f"Agent '{name}' is already registered")
        self._agents[name] = agent

    def get_agent(self, name: str) -> BaseAgent | None:
        return self._agents.get(name)

    def find_agents_for_intent(self, intent: IntentRef) -> List[BaseAgent]:
        """
        Return all agents that declare a capability for (intent.name, intent.version).
        """
        matches: List[BaseAgent] = []
        for agent in self._agents.values():
            for cap in agent.definition.capabilities:
                if cap.intent.name == intent.name and cap.intent.version == intent.version:
                    matches.append(agent)
                    break
        return matches
