"""Human- and machine-readable rendering of a ScanReport."""

from __future__ import annotations

import json

from .models import ScanReport, Severity

_COLOR = {
    Severity.CRITICAL: "\033[1;37;41m",  # white on red
    Severity.HIGH: "\033[1;31m",         # red
    Severity.MEDIUM: "\033[1;33m",       # yellow
    Severity.LOW: "\033[1;34m",          # blue
    Severity.INFO: "\033[1;30m",         # grey
}
_RESET = "\033[0m"


def render_json(report: ScanReport) -> str:
    return json.dumps(report.to_dict(), indent=2)


def render_text(report: ScanReport, *, color: bool = True) -> str:
    def c(sev: Severity, s: str) -> str:
        return f"{_COLOR[sev]}{s}{_RESET}" if color else s

    lines = []
    lines.append("")
    lines.append(f"  IntentusNet MCP Scan — {report.target}")
    lines.append(f"  transport={report.transport}  tools={report.tool_count}")
    lines.append("  " + "-" * 64)

    if report.error:
        lines.append(f"  ERROR: {report.error}")
        lines.append("")
        return "\n".join(lines)

    if not report.findings:
        lines.append("  No findings. (Note: absence of findings is not a safety guarantee.)")
        lines.append("")
        return "\n".join(lines)

    for f in report.findings:
        tag = f"[{f.severity.value.upper()}]"
        lines.append(f"  {c(f.severity, tag.ljust(10))} {f.rule_id}  {f.tool}")
        lines.append(f"      {f.title}")
        if f.evidence:
            lines.append(f"      evidence: {f.evidence}")
        lines.append(f"      → {f.recommendation}")
        lines.append("")

    counts = report.counts()
    summary = "  ".join(
        f"{c(s, s.value)}={counts[s.value]}" for s in Severity if counts[s.value]
    )
    lines.append("  " + "-" * 64)
    lines.append(f"  summary: {summary}")
    lines.append("")
    return "\n".join(lines)
