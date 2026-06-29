"""
Security rules for MCP tool definitions.

Each rule inspects a ToolDef (or the target itself) and yields Findings.
Rules are intentionally conservative and explainable: every finding carries
the evidence that triggered it so an operator can verify, not just trust.

This is the wedge value — the report a platform/security engineer wants
before they let an agent connect to an MCP server.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional

from .models import Finding, Severity, ToolDef

# --- keyword banks -----------------------------------------------------------

_SHELL_EXEC = re.compile(
    r"\b(exec|execute|eval|shell|bash|sh|cmd|command|subprocess|spawn|system|"
    r"powershell|os\.system|run_?command)\b",
    re.I,
)
_DESTRUCTIVE = re.compile(
    r"\b(delete|remove|rm\b|drop|truncate|destroy|wipe|format|kill|terminate|"
    r"revoke|overwrite)\b",
    re.I,
)
_FS_WRITE = re.compile(r"\b(write|save|create|update|append|chmod|chown)\b.*\b(file|path|disk)\b", re.I)
_NETWORK = re.compile(r"\b(fetch|http|https|url|request|curl|download|upload|webhook|post|get)\b", re.I)
_SQL = re.compile(r"\b(sql|query|database|db|select|insert|delete|update|table)\b", re.I)
_OVERBROAD = re.compile(r"\b(any|arbitrary|anything|everything|unrestricted|full access|raw)\b", re.I)

# Imperative / injection phrasing aimed at the *model*, not a human reader.
_INJECTION = re.compile(
    r"(ignore (the )?previous|disregard (the )?above|you must|you should always|"
    r"do not (tell|mention|reveal)|system prompt|</?(system|important|instructions?)>|"
    r"as an ai|before (calling|using) any other|always call this (tool|first)|"
    r"\bact as\b|override)",
    re.I,
)

_SECRET_PARAM = re.compile(
    r"(password|passwd|secret|api[_-]?key|apikey|token|credential|private[_-]?key|"
    r"access[_-]?key|auth|bearer|session)",
    re.I,
)

# stdio commands that pull untrusted code from a registry at run time.
_UNTRUSTED_LAUNCH = re.compile(r"\b(npx|uvx|pipx|bunx|npm exec|deno run)\b", re.I)


def _has_constraints(schema: dict) -> bool:
    """A string input is 'constrained' if it limits the value space."""
    if not isinstance(schema, dict):
        return False
    return any(k in schema for k in ("enum", "pattern", "maxLength", "format", "const"))


# --- per-tool rules ----------------------------------------------------------

def rule_dangerous_capability(t: ToolDef) -> Iterable[Finding]:
    blob = f"{t.name} {t.description}"
    if _SHELL_EXEC.search(blob):
        sev = Severity.CRITICAL if _SHELL_EXEC.search(t.name) else Severity.HIGH
        yield Finding(
            rule_id="MCP001",
            severity=sev,
            tool=t.name,
            title="Tool exposes shell/exec capability",
            detail="This tool appears to run arbitrary commands. An agent influenced "
                   "by prompt injection could use it for remote code execution.",
            evidence=_excerpt(blob, _SHELL_EXEC),
            recommendation="Disallow this tool for untrusted agents, or place it behind "
                           "an allowlist + human approval at the gateway.",
        )


def rule_destructive(t: ToolDef) -> Iterable[Finding]:
    blob = f"{t.name} {t.description}"
    if _DESTRUCTIVE.search(blob):
        yield Finding(
            rule_id="MCP002",
            severity=Severity.HIGH,
            tool=t.name,
            title="Tool performs destructive / irreversible action",
            detail="Destructive verbs detected. These actions cannot be safely retried "
                   "and are high-value targets for injected instructions.",
            evidence=_excerpt(blob, _DESTRUCTIVE),
            recommendation="Require explicit approval and mark as IRREVERSIBLE at the gateway; "
                           "never auto-approve for autonomous agents.",
        )


def rule_filesystem_write(t: ToolDef) -> Iterable[Finding]:
    blob = f"{t.name} {t.description}"
    if _FS_WRITE.search(blob):
        yield Finding(
            rule_id="MCP003",
            severity=Severity.MEDIUM,
            tool=t.name,
            title="Tool writes to the filesystem",
            detail="Filesystem-write capability detected. Combined with network or exec "
                   "tools this enables persistence and exfiltration.",
            evidence=_excerpt(blob, _FS_WRITE),
            recommendation="Constrain writable paths server-side; audit all writes at the gateway.",
        )


def rule_network_egress(t: ToolDef) -> Iterable[Finding]:
    blob = f"{t.name} {t.description}"
    if _NETWORK.search(blob):
        yield Finding(
            rule_id="MCP004",
            severity=Severity.MEDIUM,
            tool=t.name,
            title="Tool can reach the network (exfiltration vector)",
            detail="Outbound network capability detected. This is the primary channel for "
                   "data exfiltration once an agent is compromised.",
            evidence=_excerpt(blob, _NETWORK),
            recommendation="Egress-allowlist destinations; redact secrets from arguments at the gateway.",
        )


def rule_prompt_injection_in_description(t: ToolDef) -> Iterable[Finding]:
    if _INJECTION.search(t.description):
        yield Finding(
            rule_id="MCP005",
            severity=Severity.HIGH,
            tool=t.name,
            title="Tool description contains agent-directed instructions",
            detail="The tool description embeds imperative instructions aimed at the model "
                   "(a 'tool poisoning' / line-jumping attack). The description is read by "
                   "the agent and can hijack its behavior before any call is made.",
            evidence=_excerpt(t.description, _INJECTION),
            recommendation="Reject or sanitize this tool. Treat third-party tool descriptions "
                           "as untrusted input at the gateway.",
        )


def rule_secret_parameters(t: ToolDef) -> Iterable[Finding]:
    for pname, pschema in t.properties().items():
        if _SECRET_PARAM.search(pname):
            yield Finding(
                rule_id="MCP006",
                severity=Severity.HIGH,
                tool=t.name,
                title=f"Tool accepts a secret-bearing parameter: '{pname}'",
                detail="Credentials passed as tool arguments flow through the agent's context "
                       "and to the (possibly third-party) server, where they may be logged.",
                evidence=f"parameter '{pname}'",
                recommendation="Inject secrets server-side, not via arguments; redact this "
                               "parameter in gateway audit logs.",
            )


def rule_unconstrained_input(t: ToolDef) -> Iterable[Finding]:
    blob = f"{t.name} {t.description}"
    dangerous_sink = bool(_SHELL_EXEC.search(blob) or _SQL.search(blob) or _NETWORK.search(blob))
    if not dangerous_sink:
        return
    for pname, pschema in t.properties().items():
        if isinstance(pschema, dict) and pschema.get("type") == "string" and not _has_constraints(pschema):
            yield Finding(
                rule_id="MCP007",
                severity=Severity.MEDIUM,
                tool=t.name,
                title=f"Unconstrained string input '{pname}' feeds a dangerous sink",
                detail="A free-form string parameter reaches an exec/SQL/network sink with no "
                       "enum/pattern/maxLength, enabling injection.",
                evidence=f"parameter '{pname}' (string, no constraints)",
                recommendation="Add schema constraints (enum/pattern/maxLength) and validate at the gateway.",
            )


def rule_overbroad(t: ToolDef) -> Iterable[Finding]:
    if _OVERBROAD.search(t.description) and _SHELL_EXEC.search(f"{t.name} {t.description}"):
        yield Finding(
            rule_id="MCP008",
            severity=Severity.HIGH,
            tool=t.name,
            title="Tool advertises broad / arbitrary capability",
            detail="Description claims arbitrary or unrestricted access. Broad tools are hard "
                   "to scope and easy to abuse.",
            evidence=_excerpt(t.description, _OVERBROAD),
            recommendation="Split into narrow, well-scoped tools; deny the broad variant.",
        )


TOOL_RULES = [
    rule_dangerous_capability,
    rule_destructive,
    rule_filesystem_write,
    rule_network_egress,
    rule_prompt_injection_in_description,
    rule_secret_parameters,
    rule_unconstrained_input,
    rule_overbroad,
]


# --- target-level rules ------------------------------------------------------

def rule_untrusted_origin(target: str, transport: str) -> Iterable[Finding]:
    if transport == "stdio" and _UNTRUSTED_LAUNCH.search(target):
        yield Finding(
            rule_id="MCP010",
            severity=Severity.MEDIUM,
            tool="<server>",
            title="Server launches third-party code from a registry at runtime",
            detail="The server is started via a registry runner (npx/uvx/etc.), pulling "
                   "unpinned third-party code each run — a supply-chain risk.",
            evidence=_excerpt(target, _UNTRUSTED_LAUNCH),
            recommendation="Pin a version/digest and vendor the server; review before allowing.",
        )


def evaluate(tools: List[ToolDef], *, target: str, transport: str) -> List[Finding]:
    findings: List[Finding] = []
    findings.extend(rule_untrusted_origin(target, transport))
    for t in tools:
        for rule in TOOL_RULES:
            findings.extend(rule(t))
    # Stable, severity-first ordering.
    findings.sort(key=lambda f: (-f.severity.rank, f.tool, f.rule_id))
    return findings


def _excerpt(text: str, pattern: re.Pattern, width: int = 60) -> str:
    m = pattern.search(text)
    if not m:
        return ""
    start = max(0, m.start() - width // 2)
    end = min(len(text), m.end() + width // 2)
    snippet = text[start:end].replace("\n", " ").strip()
    return f"…{snippet}…" if start > 0 or end < len(text) else snippet
