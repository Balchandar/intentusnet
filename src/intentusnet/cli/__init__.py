"""
IntentusNet CLI - Command-line interface for execution inspection.

Commands:
- intentusnet executions list
- intentusnet executions show <id>
- intentusnet executions trace <id>
- intentusnet executions diff <id1> <id2>
- intentusnet replay <id> [--dry-run]
- intentusnet estimate <intent.json>
- intentusnet recovery scan
- intentusnet recovery resume <id>
- intentusnet recovery abort <id>

Output:
- JSON/JSONL only
- Deterministic ordering
- Grep/jq friendly
"""

from .main import main

__all__ = ["main"]
