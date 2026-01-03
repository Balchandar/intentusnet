"""
CLI entry point.
"""

import sys
import argparse
import logging

from .commands import (
    list_executions,
    show_execution,
    trace_execution,
    diff_executions,
    replay_execution,
    estimate_cost,
    scan_recovery,
    resume_execution,
    abort_execution,
)


def main() -> None:
    """
    Main CLI entry point.
    """
    parser = argparse.ArgumentParser(
        prog="intentusnet",
        description="IntentusNet - Deterministic LLM execution runtime",
    )

    parser.add_argument(
        "--wal-dir",
        default=".intentusnet/wal",
        help="WAL directory (default: .intentusnet/wal)",
    )

    parser.add_argument(
        "--record-dir",
        default=".intentusnet/records",
        help="Execution record directory (default: .intentusnet/records)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # ------------------------------------------------------------
    # executions subcommand
    # ------------------------------------------------------------
    executions_parser = subparsers.add_parser("executions", help="Execution inspection")
    exec_subparsers = executions_parser.add_subparsers(dest="subcommand", help="Execution commands")

    # list
    exec_subparsers.add_parser("list", help="List all executions")

    # show
    show_parser = exec_subparsers.add_parser("show", help="Show execution details")
    show_parser.add_argument("execution_id", help="Execution ID")

    # trace
    trace_parser = exec_subparsers.add_parser("trace", help="Show execution trace")
    trace_parser.add_argument("execution_id", help="Execution ID")

    # diff
    diff_parser = exec_subparsers.add_parser("diff", help="Diff two executions")
    diff_parser.add_argument("execution_id_1", help="First execution ID")
    diff_parser.add_argument("execution_id_2", help="Second execution ID")

    # ------------------------------------------------------------
    # replay subcommand
    # ------------------------------------------------------------
    replay_parser = subparsers.add_parser("replay", help="Replay an execution")
    replay_parser.add_argument("execution_id", help="Execution ID")
    replay_parser.add_argument("--dry-run", action="store_true", help="Dry run (no side effects)")

    # ------------------------------------------------------------
    # estimate subcommand
    # ------------------------------------------------------------
    estimate_parser = subparsers.add_parser("estimate", help="Estimate execution cost")
    estimate_parser.add_argument("intent_file", help="Intent JSON file")
    estimate_parser.add_argument("--budget", type=float, help="Budget limit")

    # ------------------------------------------------------------
    # recovery subcommand
    # ------------------------------------------------------------
    recovery_parser = subparsers.add_parser("recovery", help="Crash recovery")
    recovery_subparsers = recovery_parser.add_subparsers(dest="recovery_subcommand", help="Recovery commands")

    # scan
    recovery_subparsers.add_parser("scan", help="Scan for incomplete executions")

    # resume
    resume_parser = recovery_subparsers.add_parser("resume", help="Resume an execution")
    resume_parser.add_argument("execution_id", help="Execution ID")

    # abort
    abort_parser = recovery_subparsers.add_parser("abort", help="Abort an execution")
    abort_parser.add_argument("execution_id", help="Execution ID")
    abort_parser.add_argument("--reason", required=True, help="Abort reason")

    # ------------------------------------------------------------
    # Parse and execute
    # ------------------------------------------------------------
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    try:
        if args.command == "executions":
            if args.subcommand == "list":
                list_executions(args)
            elif args.subcommand == "show":
                show_execution(args)
            elif args.subcommand == "trace":
                trace_execution(args)
            elif args.subcommand == "diff":
                diff_executions(args)
            else:
                executions_parser.print_help()

        elif args.command == "replay":
            replay_execution(args)

        elif args.command == "estimate":
            estimate_cost(args)

        elif args.command == "recovery":
            if args.recovery_subcommand == "scan":
                scan_recovery(args)
            elif args.recovery_subcommand == "resume":
                resume_execution(args)
            elif args.recovery_subcommand == "abort":
                abort_execution(args)
            else:
                recovery_parser.print_help()

        else:
            parser.print_help()

    except Exception as e:
        if args.verbose:
            raise
        else:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
