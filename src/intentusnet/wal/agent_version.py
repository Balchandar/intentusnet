"""
Agent version tracking and pinning.

Ensures deterministic replay by tracking agent versions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict
import hashlib
import json


@dataclass
class AgentVersion:
    """Agent version information."""
    agent_name: str
    version: Optional[str] = None
    digest: Optional[str] = None  # Immutable content hash
    metadata: Dict[str, str] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def compute_digest(self, agent_code: str) -> str:
        """Compute immutable digest from agent code."""
        return hashlib.sha256(agent_code.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "version": self.version,
            "digest": self.digest,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentVersion":
        return cls(
            agent_name=data["agent_name"],
            version=data.get("version"),
            digest=data.get("digest"),
            metadata=data.get("metadata", {}),
        )

    def matches(self, other: "AgentVersion") -> bool:
        """Check if versions match."""
        if self.digest and other.digest:
            return self.digest == other.digest
        if self.version and other.version:
            return self.version == other.version
        return False


class AgentVersionRegistry:
    """
    Registry of agent versions used in executions.
    """

    def __init__(self) -> None:
        self._versions: Dict[str, AgentVersion] = {}

    def register(self, agent_version: AgentVersion) -> None:
        """Register an agent version."""
        self._versions[agent_version.agent_name] = agent_version

    def get(self, agent_name: str) -> Optional[AgentVersion]:
        """Get registered version for agent."""
        return self._versions.get(agent_name)

    def verify(self, agent_name: str, runtime_version: AgentVersion) -> bool:
        """
        Verify agent version matches registered version.

        Returns True if match, False otherwise.
        """
        registered = self.get(agent_name)
        if not registered:
            return True  # No version pinned

        return registered.matches(runtime_version)
