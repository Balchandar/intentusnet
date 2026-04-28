"""Single-command entry point: ``python demo/run_demo.py``.

Unfolds the four-act story (baseline → instrumented → replay → divergence)
and writes artefacts under ``.intentusnet/demo/`` for the CLI to inspect.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
for p in (_SRC, _REPO_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from demo.scenarios import (  # noqa: E402
    act1_baseline, act2_intentus, act3_replay_match, act4_replay_divergence,
)


DEFAULT_PROMPT = "Summarize last month's customer complaints"
DEFAULT_RECORD_DIR = ".intentusnet/demo/records"
DEFAULT_WAL_DIR = ".intentusnet/demo/wal"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_demo",
        description="IntentusNet four-act demo "
                    "(baseline → instrumented → replay → divergence).",
    )
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--record-dir", default=DEFAULT_RECORD_DIR)
    parser.add_argument("--wal-dir", default=DEFAULT_WAL_DIR)
    args = parser.parse_args(argv)

    os.makedirs(args.record_dir, exist_ok=True)
    os.makedirs(args.wal_dir, exist_ok=True)

    act1_baseline(args.prompt)

    artifacts = act2_intentus(
        args.prompt, record_dir=args.record_dir, wal_dir=args.wal_dir,
    )

    match = act3_replay_match(artifacts)
    if not match.matched:
        print("\n[!] Replay did not match. The demo cannot continue.")
        return 1

    diverged = act4_replay_divergence(artifacts)
    if diverged["result"].matched:
        print("\n[!] Expected divergence was not detected.")
        return 1

    print(
        "\nNext steps:\n"
        f"  python demo/cli.py show-trace {artifacts.execution_id} "
        f"--record-dir {args.record_dir}\n"
        f"  python demo/cli.py replay {artifacts.execution_id} "
        f"--record-dir {args.record_dir}\n"
        f"  python demo/cli.py verify-log {artifacts.execution_id} "
        f"--wal-dir {args.wal_dir}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
