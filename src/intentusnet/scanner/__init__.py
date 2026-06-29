"""
IntentusNet MCP Scanner.

Static security scanner for MCP servers. Connects to any MCP server,
enumerates its advertised tools via `tools/list`, and evaluates each
tool definition against a set of security rules:

- dangerous capabilities (shell/exec/delete)
- prompt-injection payloads embedded in tool descriptions
- secret-bearing parameters flowing to third-party servers
- unconstrained inputs feeding dangerous sinks
- untrusted supply-chain origin

This reuses the same MCP transport conventions as the IntentusNet gateway
(stdio subprocess relay, HTTP JSON-RPC) but performs read-only introspection.
"""

from .models import Finding, ScanReport, Severity, ToolDef
from .scanner import scan_target

__all__ = ["Finding", "ScanReport", "Severity", "ToolDef", "scan_target"]
