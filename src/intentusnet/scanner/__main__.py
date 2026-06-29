"""
`intentus scan` — CLI entrypoint for the MCP security scanner.

Standalone on purpose: runs via `python -m intentusnet.scanner` so it works
independently of the main CLI. Wire as a console script once stabilized:

    [project.scripts]
    intentus-scan = "intentusnet.scanner.__main__:main"

Usage:
    python -m intentusnet.scanner --http  http://localhost:5123
    python -m intentusnet.scanner --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"
    python -m intentusnet.scanner --http  http://localhost:5123 --json
    python -m intentusnet.scanner --http  http://localhost:5123 --fail-on high   # CI gate
"""

from __future__ import annotations

import argparse
import sys

from .models import Severity
from .report import render_json, render_text
from .scanner import scan_target


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="intentus scan",
        description="Security-scan an MCP server's advertised tools (read-only).",
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--http", metavar="URL", help="HTTP MCP server URL")
    src.add_argument("--stdio", metavar="CMD", help="stdio MCP server launch command")
    p.add_argument("--json", action="store_true", help="emit JSON instead of text")
    p.add_argument("--no-color", action="store_true", help="disable ANSI color")
    p.add_argument("--timeout", type=float, default=30.0, help="introspection timeout (s)")
    p.add_argument(
        "--fail-on",
        choices=[s.value for s in Severity],
        default="high",
        help="exit non-zero if any finding >= this severity (default: high)",
    )
    args = p.parse_args(argv)

    report = scan_target(stdio=args.stdio, http=args.http, timeout=args.timeout)

    if args.json:
        print(render_json(report))
    else:
        print(render_text(report, color=not args.no_color))

    if report.error:
        return 2

    threshold = Severity(args.fail_on).rank
    if any(f.severity.rank >= threshold for f in report.findings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
