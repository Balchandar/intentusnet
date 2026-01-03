"""
Record management and verification commands.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

from intentusnet.recording.store import FileExecutionStore
from intentusnet.recording.diff import ExecutionDiffer
from intentusnet.recording.consistency import ConsistencyChecker
from intentusnet.recording.record_lifecycle import RecordLifecycleManager, RecordHasher
from .output import output_json, output_table, get_output_format
from .security import require_write_mode, require_confirmation


def records_list(args) -> None:
    """List all execution records."""
    store = FileExecutionStore(args.record_dir)
    execution_ids = store.list_ids()

    output_format = get_output_format(args)
    if output_format == "json":
        output_json({"records": execution_ids, "count": len(execution_ids)})
    else:
        # Load basic info for table
        rows = []
        for execution_id in execution_ids:
            try:
                record = store.load(execution_id)
                rows.append({
                    "execution_id": execution_id,
                    "created": record.header.createdUtcIso,
                    "replayable": "yes" if record.header.replayable else "no",
                })
            except Exception:
                rows.append({
                    "execution_id": execution_id,
                    "created": "unknown",
                    "replayable": "unknown",
                })

        output_table(rows, ["execution_id", "created", "replayable"])


def records_show(args) -> None:
    """Show record details."""
    store = FileExecutionStore(args.record_dir)

    try:
        record = store.load(args.execution_id)
    except FileNotFoundError:
        print(f"Error: Record not found for execution {args.execution_id}", file=sys.stderr)
        sys.exit(1)

    output_json(record.to_dict())


def records_verify(args) -> None:
    """Verify record integrity."""
    store = FileExecutionStore(args.record_dir)

    try:
        record = store.load(args.execution_id)
        record_data = record.to_dict()
    except FileNotFoundError:
        print(f"Error: Record not found for execution {args.execution_id}", file=sys.stderr)
        sys.exit(1)

    # Verify record hash
    hash_valid = RecordHasher.verify_record_hash(record_data)

    # Determine state
    state = RecordLifecycleManager.determine_state(record_data)

    # Check WAL consistency
    checker = ConsistencyChecker(args.wal_dir, store)
    violations = checker.check(args.execution_id)

    result = {
        "execution_id": args.execution_id,
        "state": state.value,
        "hash_valid": hash_valid,
        "wal_consistent": len(violations) == 0,
        "violations": [v.to_dict() for v in violations],
    }

    output_json(result)

    # Exit code
    sys.exit(0 if (hash_valid and len(violations) == 0) else 1)


def records_diff(args) -> None:
    """Diff two execution records."""
    store = FileExecutionStore(args.record_dir)

    try:
        record1 = store.load(args.execution_id_1)
        record2 = store.load(args.execution_id_2)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    differ = ExecutionDiffer()
    diff = differ.diff(record1, record2)

    output_json(diff.to_dict())


def records_stats(args) -> None:
    """Show record statistics."""
    store = FileExecutionStore(args.record_dir)
    execution_ids = store.list_ids()

    stats = {
        "total_records": len(execution_ids),
        "replayable": 0,
        "not_replayable": 0,
        "by_intent": {},
    }

    for execution_id in execution_ids:
        try:
            record = store.load(execution_id)
            if record.header.replayable:
                stats["replayable"] += 1
            else:
                stats["not_replayable"] += 1

            # Count by intent
            intent_name = record.envelope.get("intent", {}).get("name", "unknown")
            stats["by_intent"][intent_name] = stats["by_intent"].get(intent_name, 0) + 1
        except Exception:
            pass

    output_json(stats)


@require_write_mode
@require_confirmation("garbage collection")
def records_gc(args) -> None:
    """Garbage collect old records."""
    store = FileExecutionStore(args.record_dir)
    execution_ids = store.list_ids()

    # Parse --older-than
    older_than_days = args.older_than if hasattr(args, 'older_than') else 30
    cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)

    deleted = []
    for execution_id in execution_ids:
        try:
            record = store.load(execution_id)
            created = datetime.fromisoformat(record.header.createdUtcIso.replace('Z', '+00:00'))

            if created < cutoff_date:
                # Delete record file
                record_path = Path(args.record_dir) / f"{execution_id}.json"
                record_path.unlink()
                deleted.append(execution_id)
        except Exception:
            pass

    result = {
        "deleted_count": len(deleted),
        "deleted_ids": deleted,
    }

    output_json(result)
    print(f"Deleted {len(deleted)} records older than {older_than_days} days", file=sys.stderr)
