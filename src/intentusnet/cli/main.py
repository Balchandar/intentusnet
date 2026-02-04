"""
IntentusNet CLI v2 - Production-grade command-line interface.

All commands support:
- --output json|jsonl|table
- --quiet mode
- Deterministic exit codes
"""

import sys
import argparse
import logging

# Import command modules
from .execution_commands import (
    execution_status,
    execution_wait,
    execution_abort,
    execution_verify,
)
from .wal_commands import (
    wal_inspect,
    wal_verify,
    wal_tail,
    wal_stats,
)
from .record_commands import (
    records_list,
    records_show,
    records_verify,
    records_diff,
    records_stats,
    records_gc,
)
from .commands import (
    retrieve_execution,
    replay_execution,  # Deprecated, kept for backward compatibility
    scan_recovery,
    resume_execution,
    abort_execution as recovery_abort,
)
from .agent_commands import (
    agents_list,
    agents_describe,
    agents_versions,
    agents_health,
)
from .cost_commands import (
    cost_estimate,
    cost_show,
    cost_top,
    cost_budget_status,
)
from .contract_commands import (
    contracts_validate,
    contracts_show,
    contracts_violations,
)


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser with all commands."""
    parser = argparse.ArgumentParser(
        prog="intentusnet",
        description="IntentusNet - Deterministic LLM execution runtime",
        epilog="See 'intentusnet <command> --help' for command-specific help",
    )

    # Global options
    parser.add_argument(
        "--wal-dir",
        default=".intentusnet/wal",
        help="WAL directory (default: .intentusnet/wal)",
    )
    parser.add_argument(
        "--record-dir",
        default=".intentusnet/records",
        help="Record directory (default: .intentusnet/records)",
    )
    parser.add_argument(
        "--output",
        choices=["json", "jsonl", "table"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Quiet mode (minimal output)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose logging",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ========================================================================
    # EXECUTION COMMANDS
    # ========================================================================
    execution_parser = subparsers.add_parser("execution", help="Execution lifecycle")
    exec_subparsers = execution_parser.add_subparsers(dest="subcommand")

    # execution status
    status_parser = exec_subparsers.add_parser("status", help="Show execution status")
    status_parser.add_argument("execution_id", help="Execution ID")

    # execution wait
    wait_parser = exec_subparsers.add_parser("wait", help="Wait for execution to complete")
    wait_parser.add_argument("execution_id", help="Execution ID")
    wait_parser.add_argument("--timeout", type=int, help="Timeout in seconds")

    # execution abort
    abort_parser = exec_subparsers.add_parser("abort", help="Abort execution")
    abort_parser.add_argument("execution_id", help="Execution ID")
    abort_parser.add_argument("--reason", default="Manual abort", help="Abort reason")

    # execution verify
    verify_parser = exec_subparsers.add_parser("verify", help="Verify execution integrity")
    verify_parser.add_argument("execution_id", help="Execution ID")
    verify_parser.add_argument("--replay", action="store_true", help="Verify via replay")

    # ========================================================================
    # WAL COMMANDS
    # ========================================================================
    wal_parser = subparsers.add_parser("wal", help="WAL inspection")
    wal_subparsers = wal_parser.add_subparsers(dest="subcommand")

    # wal inspect
    inspect_parser = wal_subparsers.add_parser("inspect", help="Inspect WAL entries")
    inspect_parser.add_argument("execution_id", help="Execution ID")

    # wal verify
    wal_verify_parser = wal_subparsers.add_parser("verify", help="Verify WAL integrity")
    wal_verify_parser.add_argument("execution_id", help="Execution ID")

    # wal tail
    tail_parser = wal_subparsers.add_parser("tail", help="Show last N WAL entries")
    tail_parser.add_argument("execution_id", help="Execution ID")
    tail_parser.add_argument("--lines", "-n", type=int, default=10, help="Number of lines")

    # wal stats
    wal_subparsers.add_parser("stats", help="Show WAL statistics")

    # ========================================================================
    # RECORD COMMANDS
    # ========================================================================
    records_parser = subparsers.add_parser("records", help="Record management")
    records_subparsers = records_parser.add_subparsers(dest="subcommand")

    # records list
    records_subparsers.add_parser("list", help="List all records")

    # records show
    show_parser = records_subparsers.add_parser("show", help="Show record details")
    show_parser.add_argument("execution_id", help="Execution ID")

    # records verify
    rec_verify_parser = records_subparsers.add_parser("verify", help="Verify record integrity")
    rec_verify_parser.add_argument("execution_id", help="Execution ID")

    # records diff
    diff_parser = records_subparsers.add_parser("diff", help="Diff two records")
    diff_parser.add_argument("execution_id_1", help="First execution ID")
    diff_parser.add_argument("execution_id_2", help="Second execution ID")

    # records stats
    records_subparsers.add_parser("stats", help="Show record statistics")

    # records gc
    gc_parser = records_subparsers.add_parser("gc", help="Garbage collect old records")
    gc_parser.add_argument("--older-than", type=int, default=30, help="Days (default: 30)")

    # ========================================================================
    # RETRIEVE COMMAND (Phase I corrected terminology)
    # ========================================================================
    retrieve_parser = subparsers.add_parser(
        "retrieve",
        help="Retrieve historical response from execution record (lookup, not re-execution)"
    )
    retrieve_parser.add_argument("execution_id", help="Execution ID")
    retrieve_parser.add_argument("--dry-run", action="store_true", help="Show what would be retrieved")

    # ========================================================================
    # REPLAY COMMAND (DEPRECATED - kept for backward compatibility)
    # ========================================================================
    replay_parser = subparsers.add_parser(
        "replay",
        help="[DEPRECATED: use 'retrieve'] Retrieve historical response"
    )
    replay_parser.add_argument("execution_id", help="Execution ID")
    replay_parser.add_argument("--dry-run", action="store_true", help="Dry run")

    # ========================================================================
    # RECOVERY COMMANDS
    # ========================================================================
    recovery_parser = subparsers.add_parser("recovery", help="Crash recovery")
    recovery_subparsers = recovery_parser.add_subparsers(dest="recovery_subcommand")

    # recovery scan
    recovery_subparsers.add_parser("scan", help="Scan for incomplete executions")

    # recovery resume
    resume_parser = recovery_subparsers.add_parser("resume", help="Resume execution")
    resume_parser.add_argument("execution_id", help="Execution ID")

    # recovery abort
    rec_abort_parser = recovery_subparsers.add_parser("abort", help="Abort execution")
    rec_abort_parser.add_argument("execution_id", help="Execution ID")
    rec_abort_parser.add_argument("--reason", required=True, help="Abort reason")

    # ========================================================================
    # AGENT COMMANDS
    # ========================================================================
    agents_parser = subparsers.add_parser("agents", help="Agent inspection")
    agents_subparsers = agents_parser.add_subparsers(dest="subcommand")

    # agents list
    agents_subparsers.add_parser("list", help="List agents")

    # agents describe
    describe_parser = agents_subparsers.add_parser("describe", help="Describe agent")
    describe_parser.add_argument("agent", help="Agent name")

    # agents versions
    versions_parser = agents_subparsers.add_parser("versions", help="Show agent versions")
    versions_parser.add_argument("agent", help="Agent name")

    # agents health
    agents_subparsers.add_parser("health", help="Check agent health")

    # ========================================================================
    # COST COMMANDS
    # ========================================================================
    cost_parser = subparsers.add_parser("cost", help="Cost tracking")
    cost_subparsers = cost_parser.add_subparsers(dest="subcommand")

    # cost estimate
    estimate_parser = cost_subparsers.add_parser("estimate", help="Estimate cost")
    estimate_parser.add_argument("intent_file", help="Intent JSON file")
    estimate_parser.add_argument("--budget", type=float, help="Budget limit")

    # cost show
    cost_show_parser = cost_subparsers.add_parser("show", help="Show execution cost")
    cost_show_parser.add_argument("execution_id", help="Execution ID")

    # cost top
    cost_top_parser = cost_subparsers.add_parser("top", help="Top N by cost")
    cost_top_parser.add_argument("--n", type=int, default=10, help="Number of results")

    # cost budget-status
    cost_subparsers.add_parser("budget-status", help="Show budget status")

    # ========================================================================
    # CONTRACT COMMANDS
    # ========================================================================
    contracts_parser = subparsers.add_parser("contracts", help="Contract validation")
    contracts_subparsers = contracts_parser.add_subparsers(dest="subcommand")

    # contracts validate
    validate_parser = contracts_subparsers.add_parser("validate", help="Validate contract")
    validate_parser.add_argument("intent_file", help="Intent JSON file")

    # contracts show
    con_show_parser = contracts_subparsers.add_parser("show", help="Show contracts")
    con_show_parser.add_argument("execution_id", help="Execution ID")

    # contracts violations
    violations_parser = contracts_subparsers.add_parser("violations", help="Show violations")
    violations_parser.add_argument("execution_id", help="Execution ID")

    return parser


def main() -> None:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Configure logging
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    elif args.quiet:
        logging.basicConfig(level=logging.ERROR)
    else:
        logging.basicConfig(level=logging.WARNING)

    # Dispatch commands
    try:
        if args.command == "execution":
            if args.subcommand == "status":
                execution_status(args)
            elif args.subcommand == "wait":
                execution_wait(args)
            elif args.subcommand == "abort":
                execution_abort(args)
            elif args.subcommand == "verify":
                execution_verify(args)

        elif args.command == "wal":
            if args.subcommand == "inspect":
                wal_inspect(args)
            elif args.subcommand == "verify":
                wal_verify(args)
            elif args.subcommand == "tail":
                wal_tail(args)
            elif args.subcommand == "stats":
                wal_stats(args)

        elif args.command == "records":
            if args.subcommand == "list":
                records_list(args)
            elif args.subcommand == "show":
                records_show(args)
            elif args.subcommand == "verify":
                records_verify(args)
            elif args.subcommand == "diff":
                records_diff(args)
            elif args.subcommand == "stats":
                records_stats(args)
            elif args.subcommand == "gc":
                records_gc(args)

        elif args.command == "retrieve":
            retrieve_execution(args)

        elif args.command == "replay":
            # DEPRECATED: Calls retrieve_execution with deprecation warning
            replay_execution(args)

        elif args.command == "recovery":
            if args.recovery_subcommand == "scan":
                scan_recovery(args)
            elif args.recovery_subcommand == "resume":
                resume_execution(args)
            elif args.recovery_subcommand == "abort":
                recovery_abort(args)

        elif args.command == "agents":
            if args.subcommand == "list":
                agents_list(args)
            elif args.subcommand == "describe":
                agents_describe(args)
            elif args.subcommand == "versions":
                agents_versions(args)
            elif args.subcommand == "health":
                agents_health(args)

        elif args.command == "cost":
            if args.subcommand == "estimate":
                cost_estimate(args)
            elif args.subcommand == "show":
                cost_show(args)
            elif args.subcommand == "top":
                cost_top(args)
            elif args.subcommand == "budget-status":
                cost_budget_status(args)

        elif args.command == "contracts":
            if args.subcommand == "validate":
                contracts_validate(args)
            elif args.subcommand == "show":
                contracts_show(args)
            elif args.subcommand == "violations":
                contracts_violations(args)

        else:
            parser.print_help()

    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        if args.verbose:
            raise
        else:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
