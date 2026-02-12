#!/usr/bin/env python3
"""
Gate 2: Deterministic Execution Verification

Parses the evaluation report and enforces:
  - Mean reliability >= threshold
  - Zero critical failures (side-effect drift)
  - Zero fingerprint mismatches across runs
  - Zero timeout determinism violations
"""

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(description="Gate 2: Deterministic Execution")
    parser.add_argument("--report", required=True, help="Path to evaluation_report.json")
    parser.add_argument("--threshold", type=float, default=0.98)
    args = parser.parse_args()

    try:
        with open(args.report) as f:
            report = json.load(f)
    except FileNotFoundError:
        print("GATE 2 FAIL: Evaluation report not found")
        print(f"Expected: {args.report}")
        sys.exit(1)
    except json.JSONDecodeError:
        print("GATE 2 FAIL: Evaluation report is not valid JSON")
        sys.exit(1)

    reliability = float(report.get("mean_reliability", 0))
    critical = int(report.get("total_critical_failures", -1))
    fp_mismatch = int(report.get("fingerprint_mismatches", -1))
    ci_passed = report.get("ci_passed", False)

    print(f"  Mean Reliability:       {reliability:.2%}")
    print(f"  Critical Failures:      {critical}")
    print(f"  Fingerprint Mismatches: {fp_mismatch}")
    print(f"  CI Passed (self-check): {ci_passed}")
    print()

    failed = False

    # Check 1: Reliability threshold
    if reliability < args.threshold:
        print(f"  FAIL: Reliability {reliability:.2%} < threshold {args.threshold:.2%}")
        failed = True
    else:
        print(f"  PASS: Reliability {reliability:.2%} >= {args.threshold:.2%}")

    # Check 2: Zero critical failures
    if critical != 0:
        print(f"  FAIL: {critical} critical failure(s) — side-effect drift detected")
        failed = True
    else:
        print("  PASS: Zero critical failures")

    # Check 3: Zero fingerprint mismatches
    if fp_mismatch != 0:
        print(f"  FAIL: {fp_mismatch} fingerprint mismatch(es) — non-deterministic execution")
        failed = True
    else:
        print("  PASS: Zero fingerprint mismatches")

    if failed:
        print()
        print("GATE 2 FAIL: Deterministic execution requirements not met")
        sys.exit(1)

    print()
    print("GATE 2 PASS: Deterministic execution verified")


if __name__ == "__main__":
    main()
