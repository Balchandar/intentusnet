from __future__ import annotations

import argparse
import sys

def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="deterministic_routing_demo",
        description="Compare typical glue-code routing vs centralized deterministic routing."
    )
    p.add_argument("--mode", choices=["without", "with", "mcp"], default="with")
    p.add_argument("--query", default="intent routing")
    p.add_argument("--interactive", action="store_true")
    return p.parse_args(argv)

def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    query = args.query
    if args.interactive:
        try:
            query = input("Enter query: ").strip() or query
        except EOFError:
            pass

    if args.mode == "without":
        from .without_intentusnet.run_without_intentusnet import run_without_intentusnet
        run_without_intentusnet(query=query)
        return 0

    if args.mode == "with":
        from .with_intentusnet.run_with_intentusnet import run_with_intentusnet
        run_with_intentusnet(query=query)
        return 0

    from .with_intentusnet_mcp.run_with_intentusnet_mcp import run_with_intentusnet_mcp
    run_with_intentusnet_mcp(query=query)
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
