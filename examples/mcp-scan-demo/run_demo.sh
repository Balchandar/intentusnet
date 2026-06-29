#!/usr/bin/env bash
# 30-second demo: catch a poisoned MCP tool before an agent ever runs it.
#
#   bash examples/mcp-scan-demo/run_demo.sh
#
# Exit code mirrors the scan: non-zero because the server is unsafe.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
URL="http://127.0.0.1:5199"

echo "→ starting deliberately vulnerable MCP server…"
python "$HERE/vulnerable_server.py" >/dev/null 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null' EXIT
sleep 1

echo "→ scanning it with intentus-scan (read-only; never calls a tool)…"
echo
if command -v intentus-scan >/dev/null 2>&1; then
  intentus-scan --http "$URL" --fail-on high
else
  python -m intentusnet.scanner --http "$URL" --fail-on high
fi
RESULT=$?

echo
echo "→ scan exit code: $RESULT  (non-zero = unsafe; this is your CI gate)"
exit "$RESULT"
