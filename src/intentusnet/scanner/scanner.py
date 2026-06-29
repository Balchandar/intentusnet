"""Scan orchestration: introspect a target, evaluate rules, build a report."""

from __future__ import annotations

from typing import Optional

from .introspect import introspect
from .models import ScanReport
from .rules import evaluate


def scan_target(
    *, stdio: Optional[str] = None, http: Optional[str] = None, timeout: float = 30.0
) -> ScanReport:
    """
    Scan a single MCP server.

    Read-only: enumerates tools via `tools/list` and evaluates security rules.
    Never calls `tools/call`.
    """
    try:
        target, transport, tools = introspect(stdio=stdio, http=http, timeout=timeout)
    except Exception as e:  # noqa: BLE001 - surfaced in the report, not raised
        return ScanReport(
            target=stdio or http or "<unknown>",
            transport="stdio" if stdio else "http",
            tool_count=0,
            error=f"{type(e).__name__}: {e}",
        )

    findings = evaluate(tools, target=target, transport=transport)
    return ScanReport(
        target=target,
        transport=transport,
        tool_count=len(tools),
        findings=findings,
    )
