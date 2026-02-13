"""
Gateway CLI commands for IntentusNet v1.5.1.

Commands:
    intentusnet gateway --wrap <command>     Start stdio gateway wrapping an MCP server
    intentusnet gateway --http <url>         Start HTTP gateway proxying to MCP server
    intentusnet replay <execution-id>        Fast replay (WAL playback, not re-execution)
    intentusnet executions                   List all recorded executions
    intentusnet status                       Show gateway status
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict


def gateway_start(args) -> None:
    """Start the MCP gateway proxy."""
    from intentusnet.gateway.models import GatewayConfig, GatewayMode
    from intentusnet.gateway.proxy import MCPProxyServer

    if args.wrap:
        config = GatewayConfig(
            mode=GatewayMode.STDIO,
            target_command=args.wrap,
            wal_dir=args.wal_dir if hasattr(args, "wal_dir") else ".intentusnet/gateway/wal",
            index_dir=getattr(args, "gateway_index_dir", ".intentusnet/gateway/index"),
            data_dir=getattr(args, "gateway_data_dir", ".intentusnet/gateway/data"),
        )
    elif args.http:
        config = GatewayConfig(
            mode=GatewayMode.HTTP,
            target_url=args.http,
            wal_dir=args.wal_dir if hasattr(args, "wal_dir") else ".intentusnet/gateway/wal",
            index_dir=getattr(args, "gateway_index_dir", ".intentusnet/gateway/index"),
            data_dir=getattr(args, "gateway_data_dir", ".intentusnet/gateway/data"),
        )
    else:
        print("Error: --wrap or --http required", file=sys.stderr)
        sys.exit(1)

    server = MCPProxyServer(config)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
    except Exception as e:
        print(f"Gateway error: {e}", file=sys.stderr)
        sys.exit(1)


def gateway_replay(args) -> None:
    """Fast replay an execution (WAL playback, not re-execution)."""
    from intentusnet.gateway.interceptor import ExecutionInterceptor
    from intentusnet.gateway.models import GatewayConfig
    from intentusnet.gateway.replay import GatewayReplayEngine, ReplayError

    config = GatewayConfig(
        wal_dir=_get_gateway_dir(args, "wal"),
        index_dir=_get_gateway_dir(args, "index"),
        data_dir=_get_gateway_dir(args, "data"),
    )
    config.ensure_dirs()

    interceptor = ExecutionInterceptor(config)
    engine = GatewayReplayEngine(interceptor)

    execution_id = args.execution_id
    output_format = getattr(args, "output", "table")

    try:
        if getattr(args, "summary", False):
            result = engine.replay_summary(execution_id)
            _print_output(result, output_format, "replay_summary")
        else:
            result = engine.replay(execution_id)
            _print_output(result.to_dict(), output_format, "replay")
    except ReplayError as e:
        print(f"Replay error: {e}", file=sys.stderr)
        sys.exit(1)


def gateway_executions(args) -> None:
    """List all recorded gateway executions."""
    from intentusnet.gateway.interceptor import ExecutionInterceptor
    from intentusnet.gateway.models import GatewayConfig

    config = GatewayConfig(
        wal_dir=_get_gateway_dir(args, "wal"),
        index_dir=_get_gateway_dir(args, "index"),
        data_dir=_get_gateway_dir(args, "data"),
    )
    config.ensure_dirs()

    interceptor = ExecutionInterceptor(config)
    executions = interceptor.list_executions()
    output_format = getattr(args, "output", "table")

    if output_format == "json":
        print(json.dumps(executions, indent=2))
    elif output_format == "jsonl":
        for ex in executions:
            print(json.dumps(ex))
    else:
        # Table format
        if not executions:
            print("No executions recorded.")
            return

        # Header
        print(f"{'EXECUTION ID':<40} {'STATUS':<12} {'METHOD':<15} {'TOOL':<20} {'DURATION':<12} {'STARTED'}")
        print("-" * 120)

        for ex in executions:
            eid = ex.get("execution_id", "")[:36]
            status = ex.get("status", "unknown")
            method = ex.get("method", "")
            tool = ex.get("tool_name", "") or ""
            duration = ex.get("duration_ms")
            duration_str = f"{duration:.0f}ms" if duration is not None else "-"
            started = ex.get("started_at", "")[:19]

            print(f"{eid:<40} {status:<12} {method:<15} {tool:<20} {duration_str:<12} {started}")

        print(f"\nTotal: {len(executions)} executions")


def gateway_status(args) -> None:
    """Show gateway status."""
    from intentusnet.gateway.interceptor import ExecutionInterceptor, GatewayWALWriter
    from intentusnet.gateway.models import GatewayConfig

    config = GatewayConfig(
        wal_dir=_get_gateway_dir(args, "wal"),
        index_dir=_get_gateway_dir(args, "index"),
        data_dir=_get_gateway_dir(args, "data"),
    )
    config.ensure_dirs()

    interceptor = ExecutionInterceptor(config)
    output_format = getattr(args, "output", "table")

    # Gather status
    executions = interceptor.list_executions()
    wal_ok, wal_reason = interceptor.wal.verify_integrity()

    completed = sum(1 for e in executions if e.get("status") == "completed")
    failed = sum(1 for e in executions if e.get("status") == "failed")
    partial = sum(1 for e in executions if e.get("status") == "partial")
    in_progress = sum(1 for e in executions if e.get("status") == "in_progress")

    status = {
        "gateway_version": "1.5.1",
        "wal_dir": config.wal_dir,
        "data_dir": config.data_dir,
        "index_dir": config.index_dir,
        "total_executions": len(executions),
        "completed": completed,
        "failed": failed,
        "partial": partial,
        "in_progress": in_progress,
        "wal_integrity": "OK" if wal_ok else f"CORRUPT: {wal_reason}",
        "wal_entries": interceptor.wal.entry_count,
    }

    if output_format == "json":
        print(json.dumps(status, indent=2))
    elif output_format == "jsonl":
        print(json.dumps(status))
    else:
        print("IntentusNet MCP Gateway v1.5.1")
        print("=" * 40)
        print(f"WAL directory:      {status['wal_dir']}")
        print(f"Data directory:     {status['data_dir']}")
        print(f"Index directory:    {status['index_dir']}")
        print(f"WAL integrity:      {status['wal_integrity']}")
        print(f"WAL entries:        {status['wal_entries']}")
        print()
        print("Executions:")
        print(f"  Total:            {status['total_executions']}")
        print(f"  Completed:        {status['completed']}")
        print(f"  Failed:           {status['failed']}")
        print(f"  Partial (crash):  {status['partial']}")
        print(f"  In-progress:      {status['in_progress']}")


def _get_gateway_dir(args, subdir: str) -> str:
    """Get gateway subdirectory path."""
    base = getattr(args, "gateway_dir", ".intentusnet/gateway")
    return f"{base}/{subdir}"


def _print_output(data: Dict[str, Any], fmt: str, context: str = "") -> None:
    """Print output in requested format."""
    if fmt == "json":
        print(json.dumps(data, indent=2))
    elif fmt == "jsonl":
        print(json.dumps(data))
    else:
        # Table format — pretty print key fields
        if context == "replay":
            print("Replay Result (WAL Playback)")
            print("=" * 50)
            print(f"Execution ID:       {data.get('execution_id')}")
            print(f"Status:             {data.get('status')}")
            print(f"Method:             {data.get('method')}")
            print(f"Tool:               {data.get('tool_name', '-')}")
            print(f"Request hash:       {data.get('request_hash', '')[:16]}...")
            print(f"Response hash:      {(data.get('response_hash') or '')[:16]}...")
            print(f"Started:            {data.get('started_at')}")
            print(f"Completed:          {data.get('completed_at')}")
            print(f"Duration:           {data.get('duration_ms', '-')}ms")
            print(f"WAL entries:        {len(data.get('wal_entries', []))}")
            print()

            seed = data.get("deterministic_seed", {})
            print("Deterministic Seed:")
            print(f"  Sequence:         {seed.get('sequence_number')}")
            print(f"  Timestamp:        {seed.get('timestamp_iso')}")
            print(f"  Random seed:      {seed.get('random_seed', '')[:16]}...")
            print(f"  Process ID:       {seed.get('process_id')}")
            print()

            if data.get("response"):
                resp_str = json.dumps(data["response"], indent=2)
                if len(resp_str) > 500:
                    resp_str = resp_str[:500] + "\n  ... (truncated)"
                print(f"Response:\n  {resp_str}")
            print()
            print(f"WARNING: {data.get('warning', '')}")

        elif context == "replay_summary":
            print("Replay Summary")
            print("=" * 50)
            for k, v in data.items():
                if isinstance(v, dict):
                    print(f"{k}:")
                    for sk, sv in v.items():
                        print(f"  {sk}: {sv}")
                else:
                    print(f"{k}: {v}")
        else:
            print(json.dumps(data, indent=2))
