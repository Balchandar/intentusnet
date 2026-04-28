"""IntentusNet demo CLI.

    python demo/cli.py replay <execution_id> [--record-dir DIR]
    python demo/cli.py show-trace <execution_id> [--record-dir DIR]
    python demo/cli.py verify-log <execution_id> [--wal-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
for p in (_SRC, _REPO_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from intentusnet.recording.store import FileExecutionStore  # noqa: E402
from intentusnet.security.replay_engine import SecurityReplayEngine  # noqa: E402
from intentusnet.security.types import ReplayMode  # noqa: E402
from intentusnet.wal.integrity import verify_wal_integrity  # noqa: E402

from demo.mock_agents import MockLLMAgent, MockToolAgent, baseline_run  # noqa: E402


DEFAULT_RECORD_DIR = ".intentusnet/demo/records"
DEFAULT_WAL_DIR = ".intentusnet/demo/wal"


def cmd_replay(args: argparse.Namespace) -> int:
    record = FileExecutionStore(args.record_dir).load(args.execution_id)
    engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
    llm, tool = MockLLMAgent(), MockToolAgent()
    prompt = record.envelope.get("prompt", "")
    result = engine.execute(
        record, lambda: baseline_run(llm, tool, prompt)["tool_response"],
    )
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.matched else 1


def cmd_show_trace(args: argparse.Namespace) -> int:
    record = FileExecutionStore(args.record_dir).load(args.execution_id)
    print(f"Execution {record.header.executionId}")
    print(f"  envelopeHash: {record.header.envelopeHash[:24]}…")
    print(f"  createdUtcIso: {record.header.createdUtcIso}")
    print(f"  intent: {record.envelope.get('intent_name', '<unknown>')}")
    print()
    print("Trace (parent → child):")
    for ev in record.events:
        actor = ev.payload.get("actor", ev.type)
        action = ev.payload.get("action", "")
        latency = ev.payload.get("latency_ms", 0)
        marker = "✗" if ev.payload.get("error") else "✓"
        print(f"  {marker} seq={ev.seq:>2}  {actor:<14} {action:<10} "
              f"latency={latency:>6.2f} ms")
    return 0


def cmd_verify_log(args: argparse.Namespace) -> int:
    result = verify_wal_integrity(args.wal_dir, args.execution_id)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.ok else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="intentus-demo")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("replay", help="Replay a recorded execution.")
    p.add_argument("execution_id")
    p.add_argument("--record-dir", default=DEFAULT_RECORD_DIR)
    p.set_defaults(func=cmd_replay)

    p = sub.add_parser("show-trace", help="Reconstruct the execution trace.")
    p.add_argument("execution_id")
    p.add_argument("--record-dir", default=DEFAULT_RECORD_DIR)
    p.set_defaults(func=cmd_show_trace)

    p = sub.add_parser("verify-log", help="Verify WAL hash chain integrity.")
    p.add_argument("execution_id")
    p.add_argument("--wal-dir", default=DEFAULT_WAL_DIR)
    p.set_defaults(func=cmd_verify_log)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
