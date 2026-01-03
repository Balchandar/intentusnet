"""
CLI output formatting utilities.
"""

import json
import sys
from typing import Any, List, Dict


def output_json(data: Any) -> None:
    """Output JSON to stdout."""
    print(json.dumps(data, indent=2, ensure_ascii=False))


def output_jsonl(data: List[Dict]) -> None:
    """Output JSON Lines to stdout."""
    for item in data:
        print(json.dumps(item, ensure_ascii=False))


def output_table(rows: List[Dict], columns: List[str]) -> None:
    """Output table to stdout."""
    if not rows:
        return

    # Compute column widths
    widths = {col: len(col) for col in columns}
    for row in rows:
        for col in columns:
            value = str(row.get(col, ""))
            widths[col] = max(widths[col], len(value))

    # Print header
    header = " | ".join(col.ljust(widths[col]) for col in columns)
    print(header)
    print("-" * len(header))

    # Print rows
    for row in rows:
        line = " | ".join(str(row.get(col, "")).ljust(widths[col]) for col in columns)
        print(line)


def get_output_format(args) -> str:
    """Get output format from args."""
    if hasattr(args, 'output'):
        return args.output
    return "table"  # default
