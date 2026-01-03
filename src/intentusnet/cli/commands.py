"""
CLI command implementations.
"""

import json
import sys
from pathlib import Path
from typing import Any

from intentusnet.recording.store import FileExecutionStore
from intentusnet.recording.replay import ReplayEngine
from intentusnet.recording.diff import ExecutionDiffer
from intentusnet.wal.reader import WALReader
from intentusnet.wal.recovery import RecoveryManager


def _output_json(data: Any) -> None:
    """
    Output JSON to stdout.
    """
    print(json.dumps(data, indent=2, ensure_ascii=False))


def list_executions(args) -> None:
    """
    List all executions.
    """
    store = FileExecutionStore(args.record_dir)
    execution_ids = store.list_ids()

    # Sort deterministically
    execution_ids.sort()

    _output_json({"executions": execution_ids, "count": len(execution_ids)})


def show_execution(args) -> None:
    """
    Show execution details.
    """
    store = FileExecutionStore(args.record_dir)

    try:
        record = store.load(args.execution_id)
    except FileNotFoundError:
        print(f"Error: Execution {args.execution_id} not found", file=sys.stderr)
        sys.exit(1)

    _output_json(record.to_dict())


def trace_execution(args) -> None:
    """
    Show execution trace (WAL entries).
    """
    reader = WALReader(args.wal_dir, args.execution_id)

    if not reader.exists():
        print(f"Error: WAL not found for execution {args.execution_id}", file=sys.stderr)
        sys.exit(1)

    try:
        entries = reader.read_all(verify_integrity=True)
    except Exception as e:
        print(f"Error reading WAL: {e}", file=sys.stderr)
        sys.exit(1)

    trace = {
        "execution_id": args.execution_id,
        "entries": [e.to_dict() for e in entries],
        "entry_count": len(entries),
    }

    _output_json(trace)


def diff_executions(args) -> None:
    """
    Diff two executions.
    """
    store = FileExecutionStore(args.record_dir)

    try:
        record1 = store.load(args.execution_id_1)
        record2 = store.load(args.execution_id_2)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    differ = ExecutionDiffer()
    diff = differ.diff(record1, record2)

    _output_json(diff.to_dict())


def replay_execution(args) -> None:
    """
    Replay an execution.
    """
    store = FileExecutionStore(args.record_dir)

    try:
        record = store.load(args.execution_id)
    except FileNotFoundError:
        print(f"Error: Execution {args.execution_id} not found", file=sys.stderr)
        sys.exit(1)

    engine = ReplayEngine(record)
    ok, reason = engine.is_replayable()

    if not ok:
        print(f"Error: Execution is not replayable: {reason}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        _output_json({
            "dry_run": True,
            "execution_id": args.execution_id,
            "replayable": True,
            "response": record.finalResponse,
        })
    else:
        result = engine.replay()
        _output_json({
            "execution_id": result.execution_id,
            "response": result.response,
            "envelope_hash_ok": result.envelope_hash_ok,
        })


def estimate_cost(args) -> None:
    """
    Estimate execution cost from intent file.
    """
    intent_path = Path(args.intent_file)

    if not intent_path.exists():
        print(f"Error: Intent file not found: {args.intent_file}", file=sys.stderr)
        sys.exit(1)

    with open(intent_path, "r", encoding="utf-8") as f:
        intent_data = json.load(f)

    # TODO: Parse intent and run estimator
    # For now, output placeholder
    estimate = {
        "intent_file": args.intent_file,
        "estimated_cost": 100.0,
        "budget_limit": args.budget,
        "exceeds_budget": (args.budget is not None and 100.0 > args.budget),
        "note": "Cost estimation requires runtime context (not yet implemented in CLI)",
    }

    _output_json(estimate)


def scan_recovery(args) -> None:
    """
    Scan for incomplete executions.
    """
    recovery_mgr = RecoveryManager(args.wal_dir)
    incomplete = recovery_mgr.scan_incomplete_executions()

    results = []
    for execution_id in incomplete:
        decision = recovery_mgr.analyze_execution(execution_id)
        results.append({
            "execution_id": execution_id,
            "can_resume": decision.can_resume,
            "reason": decision.reason,
            "state": decision.state.value,
            "completed_steps": decision.completed_steps,
            "irreversible_steps_executed": decision.irreversible_steps_executed,
        })

    _output_json({"incomplete_executions": results, "count": len(results)})


def resume_execution(args) -> None:
    """
    Resume an incomplete execution.
    """
    recovery_mgr = RecoveryManager(args.wal_dir)

    try:
        decision = recovery_mgr.resume_execution(args.execution_id)
        _output_json({
            "resumed": True,
            "execution_id": decision.execution_id,
            "state": decision.state.value,
            "completed_steps": decision.completed_steps,
        })
    except Exception as e:
        print(f"Error: Cannot resume execution: {e}", file=sys.stderr)
        sys.exit(1)


def abort_execution(args) -> None:
    """
    Abort an execution.
    """
    recovery_mgr = RecoveryManager(args.wal_dir)

    try:
        recovery_mgr.abort_execution(args.execution_id, args.reason)
        _output_json({
            "aborted": True,
            "execution_id": args.execution_id,
            "reason": args.reason,
        })
    except Exception as e:
        print(f"Error: Cannot abort execution: {e}", file=sys.stderr)
        sys.exit(1)
