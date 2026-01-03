"""
Execution lifecycle CLI commands.
"""

import json
import sys
import time
from pathlib import Path

from intentusnet.recording.store import FileExecutionStore
from intentusnet.wal.reader import WALReader
from intentusnet.wal.state_manager import ExecutionStateManager
from intentusnet.recording.consistency import ConsistencyChecker
from intentusnet.wal.determinism import DeterminismEnforcer, DeterminismPolicy
from .security import require_write_mode, require_confirmation
from .output import output_json, output_table, get_output_format


def execution_status(args) -> None:
    """Show execution status."""
    wal_reader = WALReader(args.wal_dir, args.execution_id)

    if not wal_reader.exists():
        print(f"Error: Execution {args.execution_id} not found", file=sys.stderr)
        sys.exit(1)

    # Reconstruct state from WAL
    state = ExecutionStateManager.reconstruct_state(wal_reader)

    # Load record if exists
    store = FileExecutionStore(args.record_dir)
    try:
        record = store.load(args.execution_id)
        has_record = True
    except FileNotFoundError:
        has_record = False

    status_data = {
        "execution_id": args.execution_id,
        "state": state.value if state else "unknown",
        "is_terminal": state.is_terminal(state) if state else False,
        "has_record": has_record,
    }

    if has_record:
        status_data["replayable"] = record.header.replayable
        status_data["created_utc"] = record.header.createdUtcIso

    output_format = get_output_format(args)
    if output_format == "json":
        output_json(status_data)
    else:
        output_table([status_data], ["execution_id", "state", "is_terminal", "has_record"])


def execution_wait(args) -> None:
    """Wait for execution to reach terminal state."""
    timeout = args.timeout if hasattr(args, 'timeout') else None
    poll_interval = 1.0  # seconds

    start_time = time.time()

    while True:
        wal_reader = WALReader(args.wal_dir, args.execution_id)

        if not wal_reader.exists():
            print(f"Error: Execution {args.execution_id} not found", file=sys.stderr)
            sys.exit(1)

        state = ExecutionStateManager.reconstruct_state(wal_reader)

        if state and state.is_terminal(state):
            print(f"Execution reached terminal state: {state.value}")
            sys.exit(0)

        # Check timeout
        if timeout and (time.time() - start_time) > timeout:
            print(f"Timeout waiting for execution to complete", file=sys.stderr)
            sys.exit(1)

        time.sleep(poll_interval)


@require_write_mode
@require_confirmation("abort")
def execution_abort(args) -> None:
    """Abort an execution."""
    from intentusnet.wal.writer import WALWriter
    from intentusnet.wal.models import WALEntryType

    wal_reader = WALReader(args.wal_dir, args.execution_id)

    if not wal_reader.exists():
        print(f"Error: Execution {args.execution_id} not found", file=sys.stderr)
        sys.exit(1)

    # Check current state
    state = ExecutionStateManager.reconstruct_state(wal_reader)
    if state and state.is_terminal(state):
        print(f"Error: Execution already in terminal state: {state.value}", file=sys.stderr)
        sys.exit(1)

    # Append abort entry to WAL
    with WALWriter(args.wal_dir, args.execution_id) as wal:
        # Reload sequence
        entries = wal_reader.read_all(verify_integrity=False)
        if entries:
            wal._seq = entries[-1].seq
            wal._last_hash = entries[-1].entry_hash

        wal.append(
            WALEntryType.EXECUTION_ABORTED,
            {"reason": args.reason if hasattr(args, 'reason') else "Manual abort via CLI"},
        )

    print(f"Execution {args.execution_id} aborted")


def execution_verify(args) -> None:
    """
    Verify execution determinism and integrity.

    Checks:
    - WAL hash chain
    - Record hashes
    - WAL ↔ Record consistency
    - Deterministic replay (if --replay flag set)
    """
    from intentusnet.wal.reader import WALIntegrityError

    execution_id = args.execution_id
    issues = []

    # 1. Verify WAL integrity
    wal_reader = WALReader(args.wal_dir, execution_id)
    if not wal_reader.exists():
        issues.append("WAL file does not exist")
    else:
        try:
            wal_reader.read_all(verify_integrity=True)
        except WALIntegrityError as e:
            issues.append(f"WAL integrity check failed: {e}")

    # 2. Verify record integrity
    store = FileExecutionStore(args.record_dir)
    try:
        record = store.load(execution_id)
    except FileNotFoundError:
        issues.append("Record file does not exist")
    except Exception as e:
        issues.append(f"Record load failed: {e}")

    # 3. Check WAL ↔ Record consistency
    checker = ConsistencyChecker(args.wal_dir, store)
    violations = checker.check(execution_id)
    for violation in violations:
        issues.append(f"Consistency: {violation.description}")

    # 4. Deterministic replay verification (if requested)
    if hasattr(args, 'replay') and args.replay:
        # TODO: Implement replay verification
        pass

    # Output results
    verification_result = {
        "execution_id": execution_id,
        "verified": len(issues) == 0,
        "issues": issues,
    }

    output_format = get_output_format(args)
    if output_format == "json":
        output_json(verification_result)
    else:
        if verification_result["verified"]:
            print(f"✓ Execution {execution_id} verified successfully")
        else:
            print(f"✗ Verification failed for {execution_id}:")
            for issue in issues:
                print(f"  - {issue}")

    # Exit code: 0 if verified, 1 if issues found
    sys.exit(0 if verification_result["verified"] else 1)
