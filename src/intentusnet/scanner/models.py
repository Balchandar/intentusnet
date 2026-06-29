"""Data models for the MCP scanner."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Severity(str, Enum):
    """Finding severity, ordered for comparison via `rank`."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def rank(self) -> int:
        return {
            Severity.CRITICAL: 4,
            Severity.HIGH: 3,
            Severity.MEDIUM: 2,
            Severity.LOW: 1,
            Severity.INFO: 0,
        }[self]


@dataclass
class ToolDef:
    """A single tool advertised by an MCP server (`tools/list` entry)."""

    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mcp(cls, entry: Dict[str, Any]) -> "ToolDef":
        return cls(
            name=str(entry.get("name", "")),
            description=str(entry.get("description", "") or ""),
            input_schema=entry.get("inputSchema") or entry.get("input_schema") or {},
            raw=entry,
        )

    def properties(self) -> Dict[str, Any]:
        """Return JSON-schema properties for this tool's input."""
        props = self.input_schema.get("properties")
        return props if isinstance(props, dict) else {}


@dataclass
class Finding:
    """A single security finding against a tool (or the server itself)."""

    rule_id: str
    severity: Severity
    tool: str          # tool name, or "<server>" for server-level findings
    title: str
    detail: str
    evidence: str = ""
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "tool": self.tool,
            "title": self.title,
            "detail": self.detail,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
        }


@dataclass
class ScanReport:
    """Result of scanning one MCP server."""

    target: str
    transport: str
    tool_count: int
    findings: List[Finding] = field(default_factory=list)
    error: Optional[str] = None

    def max_severity(self) -> Optional[Severity]:
        if not self.findings:
            return None
        return max((f.severity for f in self.findings), key=lambda s: s.rank)

    def counts(self) -> Dict[str, int]:
        out = {s.value: 0 for s in Severity}
        for f in self.findings:
            out[f.severity.value] += 1
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target,
            "transport": self.transport,
            "tool_count": self.tool_count,
            "max_severity": self.max_severity().value if self.max_severity() else None,
            "counts": self.counts(),
            "findings": [f.to_dict() for f in self.findings],
            "error": self.error,
        }
