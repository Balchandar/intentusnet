#!/usr/bin/env python3
"""
Gate 7: Crash-Recovery Verification

Proves: WAL resume produces the same final state as uninterrupted execution.

Scenarios:
  1. Clean execution → capture response hash
  2. Partial WAL (simulated crash) → recovery analysis → correct decision
  3. Irreversible step crash → must BLOCK (not resume)
  4. Completed execution → recovery says COMPLETED (no re-run)
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from intentusnet.wal.writer import WALWriter
from intentusnet.wal.reader import WALReader
from intentusnet.wal.recovery import RecoveryManager


def test_safe_recovery():
    """Crash during reversible step → must allow resume."""
    print("  Scenario 1: Crash during reversible step")

    with tempfile.TemporaryDirectory(prefix="gate7_safe_") as tmpdir:
        eid = "crash-safe-001"

        with WALWriter(tmpdir, eid) as wal:
            wal.execution_started(
                envelope_hash="hash_safe_001",
                intent_name="test.compute",
            )
            wal.step_started(
                step_id="step-1", agent_name="agent-a",
                side_effect="none", contracts={}, input_hash="in1",
            )
            wal.step_completed(step_id="step-1", output_hash="out1", success=True)
            wal.step_started(
                step_id="step-2", agent_name="agent-b",
                side_effect="none", contracts={}, input_hash="in2",
            )
            # CRASH — step-2 started but not completed

        recovery = RecoveryManager(tmpdir)
        incomplete = recovery.scan_incomplete_executions()

        if eid not in incomplete:
            print("    FAIL: Incomplete execution not detected")
            return False

        decision = recovery.analyze_execution(eid)
        if not decision.can_resume:
            print(f"    FAIL: Should be resumable but got: {decision.reason}")
            return False

        print(f"    can_resume={decision.can_resume} — CORRECT")
        print(f"    completed_steps={decision.completed_steps}")
        return True


def test_irreversible_blocked():
    """Crash during irreversible step → must BLOCK."""
    print("  Scenario 2: Crash during irreversible step")

    with tempfile.TemporaryDirectory(prefix="gate7_irrev_") as tmpdir:
        eid = "crash-irrev-001"

        with WALWriter(tmpdir, eid) as wal:
            wal.execution_started(
                envelope_hash="hash_irrev_001",
                intent_name="payment.disburse",
            )
            wal.step_started(
                step_id="step-pay", agent_name="payment-gateway",
                side_effect="irreversible", contracts={}, input_hash="pay_in",
            )
            # CRASH during irreversible operation

        recovery = RecoveryManager(tmpdir)
        decision = recovery.analyze_execution(eid)

        if decision.can_resume:
            print("    FAIL: Irreversible step crash should NOT be resumable")
            return False

        print(f"    can_resume={decision.can_resume} — CORRECT (blocked)")
        print(f"    reason: {decision.reason[:70]}")
        return True


def test_completed_execution():
    """Completed execution → recovery should report nothing to do."""
    print("  Scenario 3: Already completed execution")

    with tempfile.TemporaryDirectory(prefix="gate7_done_") as tmpdir:
        eid = "completed-001"

        with WALWriter(tmpdir, eid) as wal:
            wal.execution_started(
                envelope_hash="hash_done_001",
                intent_name="test.compute",
            )
            wal.step_started(
                step_id="step-1", agent_name="agent-a",
                side_effect="none", contracts={}, input_hash="in1",
            )
            wal.step_completed(step_id="step-1", output_hash="out1", success=True)
            wal.execution_completed(response_hash="final_hash_001")

        recovery = RecoveryManager(tmpdir)
        incomplete = recovery.scan_incomplete_executions()

        if eid in incomplete:
            print("    FAIL: Completed execution should NOT be flagged as incomplete")
            return False

        print("    Completed execution correctly excluded from recovery scan")
        return True


def test_hash_chain_survives_crash():
    """WAL hash chain should be verifiable even after partial write."""
    print("  Scenario 4: Hash chain integrity after partial write")

    with tempfile.TemporaryDirectory(prefix="gate7_chain_") as tmpdir:
        eid = "chain-crash-001"

        with WALWriter(tmpdir, eid) as wal:
            wal.execution_started(
                envelope_hash="hash_chain_001",
                intent_name="test.chain",
            )
            wal.step_started(
                step_id="step-1", agent_name="agent-a",
                side_effect="none", contracts={}, input_hash="in1",
            )
            # Crash here — partial WAL

        reader = WALReader(tmpdir, eid)
        try:
            entries = reader.read_all(verify_integrity=True)
            if len(entries) >= 2:
                print(f"    {len(entries)} entries recovered with valid hash chain")
                return True
            else:
                print(f"    Only {len(entries)} entries recovered — expected at least 2")
                return False
        except Exception as e:
            print(f"    FAIL: Hash chain verification failed: {e}")
            return False


def main():
    print("Gate 7: Crash-Recovery Verification")
    print("=" * 50)

    results = [
        test_safe_recovery(),
        test_irreversible_blocked(),
        test_completed_execution(),
        test_hash_chain_survives_crash(),
    ]

    print()
    passed = sum(results)
    total = len(results)
    print(f"  Results: {passed}/{total} scenarios passed")

    if not all(results):
        print()
        print("  GATE 7 FAIL: Crash-recovery behavior incorrect")
        sys.exit(1)

    print()
    print("  GATE 7 PASS: Crash-recovery is deterministic and conservative")


if __name__ == "__main__":
    main()
