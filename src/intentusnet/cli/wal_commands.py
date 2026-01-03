"""
WAL inspection and verification commands.
"""

import json
import sys
from pathlib import Path

from intentusnet.wal.reader import WALReader, WALIntegrityError
from .output import output_json, output_table, get_output_format


def wal_inspect(args) -> None:
    """Inspect WAL entries for an execution."""
    reader = WALReader(args.wal_dir, args.execution_id)

    if not reader.exists():
        print(f"Error: WAL not found for execution {args.execution_id}", file=sys.stderr)
        sys.exit(1)

    try:
        entries = reader.read_all(verify_integrity=True)
    except WALIntegrityError as e:
        print(f"Error: WAL integrity check failed: {e}", file=sys.stderr)
        sys.exit(1)

    output_format = get_output_format(args)
    if output_format == "json":
        output_json({
            "execution_id": args.execution_id,
            "entries": [e.to_dict() for e in entries],
            "entry_count": len(entries),
        })
    else:
        # Table output
        rows = [
            {
                "seq": e.seq,
                "type": e.entry_type.value,
                "timestamp": e.timestamp_iso,
            }
            for e in entries
        ]
        output_table(rows, ["seq", "type", "timestamp"])


def wal_verify(args) -> None:
    """Verify WAL integrity."""
    reader = WALReader(args.wal_dir, args.execution_id)

    if not reader.exists():
        print(f"Error: WAL not found for execution {args.execution_id}", file=sys.stderr)
        sys.exit(1)

    try:
        entries = reader.read_all(verify_integrity=True)
        result = {
            "execution_id": args.execution_id,
            "verified": True,
            "entry_count": len(entries),
        }
        print(f"✓ WAL verified: {len(entries)} entries")
        output_json(result) if get_output_format(args) == "json" else None
        sys.exit(0)
    except WALIntegrityError as e:
        result = {
            "execution_id": args.execution_id,
            "verified": False,
            "error": str(e),
        }
        print(f"✗ WAL verification failed: {e}", file=sys.stderr)
        output_json(result) if get_output_format(args) == "json" else None
        sys.exit(1)


def wal_tail(args) -> None:
    """Show last N WAL entries."""
    reader = WALReader(args.wal_dir, args.execution_id)

    if not reader.exists():
        print(f"Error: WAL not found for execution {args.execution_id}", file=sys.stderr)
        sys.exit(1)

    entries = list(reader.iter_entries())
    n = args.lines if hasattr(args, 'lines') else 10

    tail_entries = entries[-n:]

    output_format = get_output_format(args)
    if output_format == "json":
        output_json({
            "execution_id": args.execution_id,
            "entries": [e.to_dict() for e in tail_entries],
        })
    else:
        for entry in tail_entries:
            print(f"[{entry.seq}] {entry.entry_type.value} @ {entry.timestamp_iso}")
            print(f"  {json.dumps(entry.payload, indent=2)}")


def wal_stats(args) -> None:
    """Show WAL statistics across all executions."""
    wal_dir = Path(args.wal_dir)

    if not wal_dir.exists():
        print(f"Error: WAL directory does not exist: {wal_dir}", file=sys.stderr)
        sys.exit(1)

    stats = {
        "total_wal_files": 0,
        "total_entries": 0,
        "corrupted": 0,
        "by_state": {},
    }

    for wal_file in wal_dir.glob("*.wal"):
        execution_id = wal_file.stem
        stats["total_wal_files"] += 1

        reader = WALReader(str(wal_dir), execution_id)
        try:
            entries = reader.read_all(verify_integrity=True)
            stats["total_entries"] += len(entries)

            # Determine state
            last_entry = entries[-1] if entries else None
            if last_entry:
                entry_type = last_entry.entry_type.value
                stats["by_state"][entry_type] = stats["by_state"].get(entry_type, 0) + 1
        except WALIntegrityError:
            stats["corrupted"] += 1

    output_json(stats)
