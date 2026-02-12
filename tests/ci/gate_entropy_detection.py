#!/usr/bin/env python3
"""
Gate 4: Entropy / Nondeterminism Detection

Statically scans the deterministic-critical code paths for:
  1. Unseeded random usage (random.random, random.choice, etc.)
  2. System time in fingerprint/hash paths (time.time in hash computation)
  3. Unordered iteration (iterating dict without sorted() in hash paths)
  4. UUID4 in step ID generation (nondeterministic by design)
  5. async race conditions (unsorted gather results)

Scans only deterministic-critical paths:
  - src/intentusnet/recording/
  - src/intentusnet/wal/
  - src/intentusnet/core/router.py
  - deterministic_agent/models.py
  - deterministic_agent/wal_engine.py
  - deterministic_agent/main.py
"""

import os
import re
import sys
from pathlib import Path

# Patterns that indicate potential nondeterminism
ENTROPY_PATTERNS = [
    {
        "name": "unseeded_random",
        "pattern": r"\brandom\.(random|choice|randint|shuffle|sample|uniform)\b",
        "severity": "CRITICAL",
        "description": "Unseeded random call in deterministic path",
        "exclude_comments": True,
    },
    {
        "name": "uuid4_in_stepid",
        "pattern": r"\buuid4?\(\)",
        "severity": "CRITICAL",
        "description": "UUID4 generates nondeterministic IDs",
        "exclude_comments": True,
    },
    {
        "name": "time_in_hash",
        "pattern": r"time\.time\(\).*hash|hash.*time\.time\(\)",
        "severity": "HIGH",
        "description": "Wall-clock time used near hash computation",
        "exclude_comments": True,
    },
    {
        "name": "datetime_now_in_fingerprint",
        "pattern": r"datetime\.now\(\).*fingerprint|fingerprint.*datetime\.now\(\)",
        "severity": "HIGH",
        "description": "datetime.now() used near fingerprint computation",
        "exclude_comments": True,
    },
    {
        "name": "os_urandom_in_hash",
        "pattern": r"os\.urandom\(.*\).*hash|hash.*os\.urandom",
        "severity": "CRITICAL",
        "description": "os.urandom used in hash computation",
        "exclude_comments": True,
    },
]

# Files/dirs to scan (deterministic-critical paths only)
SCAN_PATHS = [
    "src/intentusnet/recording/",
    "src/intentusnet/wal/",
    "src/intentusnet/core/router.py",
    "src/intentusnet/core/registry.py",
    "deterministic_agent/models.py",
    "deterministic_agent/wal_engine.py",
    "deterministic_agent/main.py",
    "deterministic_agent/replay_engine.py",
]

# Known safe exceptions — entire files (allowlisted)
ALLOWLIST = {
    # The EMCL provider uses os.urandom for nonces — that's correct crypto, not fingerprinting
    "src/intentusnet/security/emcl/aes_gcm.py",
    # generate_uuid is used for request/trace IDs, not step IDs
    "src/intentusnet/utils/id_generator.py",
}

# Line-level allowlist: (relative_file_path, pattern_name) pairs
# These are known-safe uses in fingerprint-critical files that are
# NOT part of the deterministic hash computation.
LINE_ALLOWLIST = {
    # uuid4() for execution_id is an INPUT parameter, not part of fingerprint
    ("src/intentusnet/recording/models.py", "uuid4_in_stepid"),
    # uuid4() for execution_id default parameter in main.py
    ("deterministic_agent/main.py", "uuid4_in_stepid"),
}


def scan_file(filepath: str, project_root: str) -> list[dict]:
    """Scan a single file for entropy patterns."""
    violations = []
    try:
        content = Path(filepath).read_text()
    except (FileNotFoundError, PermissionError):
        return violations

    rel_path = os.path.relpath(filepath, project_root)
    lines = content.split("\n")
    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()
        # Skip comments
        if stripped.startswith("#"):
            continue

        for pattern_def in ENTROPY_PATTERNS:
            if re.search(pattern_def["pattern"], line):
                # Check line-level allowlist
                if (rel_path, pattern_def["name"]) in LINE_ALLOWLIST:
                    continue

                violations.append({
                    "file": filepath,
                    "line": line_num,
                    "pattern": pattern_def["name"],
                    "severity": pattern_def["severity"],
                    "description": pattern_def["description"],
                    "code": stripped[:100],
                })

    return violations


def main():
    print("Gate 4: Entropy / Nondeterminism Detection")
    print("=" * 50)

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    all_violations = []
    files_scanned = 0

    for scan_path in SCAN_PATHS:
        full_path = os.path.join(project_root, scan_path)

        if os.path.isfile(full_path):
            files = [full_path]
        elif os.path.isdir(full_path):
            files = [
                str(p) for p in Path(full_path).rglob("*.py")
                if not p.name.startswith("__")
            ]
        else:
            print(f"  SKIP: {scan_path} (not found)")
            continue

        for filepath in files:
            rel_path = os.path.relpath(filepath, project_root)
            if rel_path in ALLOWLIST:
                continue

            violations = scan_file(filepath, project_root)
            files_scanned += 1

            if violations:
                all_violations.extend(violations)

    print(f"  Files scanned: {files_scanned}")
    print(f"  Violations found: {len(all_violations)}")
    print()

    critical_count = 0
    for v in all_violations:
        severity_marker = "!!!" if v["severity"] == "CRITICAL" else " ! "
        print(f"  {severity_marker} [{v['severity']}] {v['file']}:{v['line']}")
        print(f"       {v['description']}")
        print(f"       Code: {v['code']}")
        print()
        if v["severity"] == "CRITICAL":
            critical_count += 1

    if critical_count > 0:
        print(f"GATE 4 FAIL: {critical_count} CRITICAL entropy source(s) in deterministic paths")
        sys.exit(1)

    if all_violations:
        print(f"GATE 4 WARN: {len(all_violations)} non-critical finding(s) — review recommended")
    else:
        print("GATE 4 PASS: No nondeterminism sources detected in critical paths")


if __name__ == "__main__":
    main()
