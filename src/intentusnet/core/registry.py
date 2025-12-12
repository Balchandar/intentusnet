from __future__ import annotations

"""
AgentRegistry

Central registry of all agents (local + remote) in a single IntentusNet runtime.

Responsibilities:
  - Hold a mapping of agent name → BaseAgent instance
  - Find agents that can handle a given IntentRef
  - Provide helpers to inspect agents by node (local vs remote)
  - Enforce uniqueness of agent names
"""

from typing import Dict, List, Optional

from ..protocol.intent import IntentRef
from .agent import BaseAgent


class AgentRegistry:
    """
    Simple in-memory registry for agents.

    This is intentionally small and synchronous. It is meant to be:
      - used by a single runtime
      - queried by the router
      - extended later if we add dynamic loading / hot-reload

    It is NOT:
      - a distributed service
      - a persistence layer
    """

    def __init__(self) -> None:
        # name -> BaseAgent
        self._agents: Dict[str, BaseAgent] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def register(self, agent: BaseAgent) -> None:
        """
        Register a new agent instance.

        Names must be unique within a runtime.
        """
        name = agent.definition.name
        if name in self._agents:
            raise ValueError(f"Agent '{name}' is already registered")
        self._agents[name] = agent

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    def get_agent(self, name: str) -> Optional[BaseAgent]:
        """
        Return a single agent by name or None if not found.
        """
        return self._agents.get(name)

    def all_agents(self) -> List[BaseAgent]:
        """
        Return all registered agents.
        """
        return list(self._agents.values())

    def agents_for_node(self, node_id: Optional[str]) -> List[BaseAgent]:
        """
        Return all agents hosted on a specific node.

        node_id:
          - None → local agents
          - "node-x" → remote agents for that node
        """
        result: List[BaseAgent] = []
        for agent in self._agents.values():
            if agent.definition.nodeId == node_id:
                result.append(agent)
        return result

    # ------------------------------------------------------------------
    # Intent-based resolution
    # ------------------------------------------------------------------
    def find_agents_for_intent(self, intent: IntentRef) -> List[BaseAgent]:
        """
        Return all agents that declare a capability for (intent.name, intent.version).

        Matching rules:
          - Exact match on name + version
          - Or wildcard support:
              * capability.intent.name == "*" matches any intent name
              * capability.intent.version == "*" matches any version
        """
        matches: List[BaseAgent] = []

        for agent in self._agents.values():
            for cap in agent.definition.capabilities:
                cap_intent = cap.intent

                # Name match (exact or wildcard)
                name_ok = cap_intent.name == intent.name or cap_intent.name == "*"

                # Version match (exact or wildcard)
                version_ok = cap_intent.version == intent.version or cap_intent.version == "*"

                if name_ok and version_ok:
                    matches.append(agent)
                    break  # no need to check other capabilities for this agent

        return matches

    def find_local_agents_for_intent(self, intent: IntentRef) -> List[BaseAgent]:
        """
        Return only *local* agents that can handle this intent.
        """
        return [a for a in self.find_agents_for_intent(intent) if a.definition.nodeId is None]

    def find_remote_agents_for_intent(self, intent: IntentRef) -> List[BaseAgent]:
        """
        Return only *remote* agents that can handle this intent.
        """
        return [a for a in self.find_agents_for_intent(intent) if a.definition.nodeId is not None]
