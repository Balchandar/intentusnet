#!/usr/bin/env python3
"""
Gate 8: WAL Integrity & Tamper Detection

Proves:
  1. Hash chain is intact after write
  2. Tampered entry is detected (hash mismatch)
  3. Signed WAL entries have valid Ed25519 signatures
  4. Tampered signed entry fails signature verification
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from intentusnet.wal.writer import WALWriter
from intentusnet.wal.reader import WALReader
from intentusnet.wal.signing import Ed25519WALSigner, Ed25519WALVerifier


def test_hash_chain_integrity():
    """Write WAL entries and verify the hash chain is intact."""
    print("  Test 1: Hash chain integrity")

    with tempfile.TemporaryDirectory(prefix="gate8_chain_") as tmpdir:
        eid = "integrity-001"

        with WALWriter(tmpdir, eid) as wal:
            wal.execution_started(envelope_hash="env_hash_001", intent_name="test.chain")
            wal.step_started(
                step_id="s1", agent_name="agent-a",
                side_effect="none", contracts={}, input_hash="in1",
            )
            wal.step_completed(step_id="s1", output_hash="out1", success=True)
            wal.step_started(
                step_id="s2", agent_name="agent-b",
                side_effect="none", contracts={}, input_hash="in2",
            )
            wal.step_completed(step_id="s2", output_hash="out2", success=True)
            wal.execution_completed(response_hash="final_hash_001")

        reader = WALReader(tmpdir, eid)
        entries = reader.read_all(verify_integrity=True)

        # Verify chain linkage
        for i in range(1, len(entries)):
            if entries[i].prev_hash != entries[i - 1].entry_hash:
                print(f"    FAIL: Chain broken at seq {entries[i].seq}")
                return False

        print(f"    {len(entries)} entries — hash chain intact")
        return True


def test_tamper_detection():
    """Modify a WAL entry and verify hash mismatch is detected."""
    print("  Test 2: Tamper detection")

    with tempfile.TemporaryDirectory(prefix="gate8_tamper_") as tmpdir:
        eid = "tamper-001"

        with WALWriter(tmpdir, eid) as wal:
            wal.execution_started(envelope_hash="env_hash_002", intent_name="test.tamper")
            wal.step_started(
                step_id="s1", agent_name="agent-a",
                side_effect="none", contracts={}, input_hash="in1",
            )
            wal.step_completed(step_id="s1", output_hash="out1", success=True)
            wal.execution_completed(response_hash="final_hash_002")

        reader = WALReader(tmpdir, eid)
        entries = reader.read_all(verify_integrity=True)

        # Tamper with the step_completed entry
        tampered = entries[2]  # STEP_COMPLETED
        original_hash = tampered.entry_hash
        tampered.payload["success"] = False
        new_hash = tampered.compute_hash()

        if original_hash == new_hash:
            print("    FAIL: Tampered payload produced the same hash")
            return False

        print(f"    Original hash: {original_hash[:24]}...")
        print(f"    Tampered hash: {new_hash[:24]}...")
        print("    Tamper correctly detected via hash mismatch")
        return True


def test_signed_wal_valid():
    """Write signed WAL and verify all signatures are valid."""
    print("  Test 3: Signed WAL verification")

    with tempfile.TemporaryDirectory(prefix="gate8_signed_") as tmpdir:
        signer = Ed25519WALSigner.generate()
        eid = "signed-001"

        with WALWriter(tmpdir, eid, signer=signer) as wal:
            wal.execution_started(envelope_hash="env_hash_003", intent_name="test.signed")
            wal.step_started(
                step_id="s1", agent_name="agent-a",
                side_effect="none", contracts={}, input_hash="in1",
            )
            wal.step_completed(step_id="s1", output_hash="out1", success=True)
            wal.execution_completed(response_hash="final_hash_003")

        verifier = Ed25519WALVerifier()
        verifier.add_from_signer(signer)

        reader = WALReader(tmpdir, eid)
        entries = reader.read_all(verify_integrity=True)

        all_valid = True
        for entry in entries:
            if not entry.is_signed:
                print(f"    FAIL: Entry seq={entry.seq} is NOT signed")
                all_valid = False
                continue

            valid = entry.verify_signature(verifier)
            if not valid:
                print(f"    FAIL: Entry seq={entry.seq} signature INVALID")
                all_valid = False

        if all_valid:
            print(f"    {len(entries)} entries — all signatures VALID")
        return all_valid


def test_signed_tamper_detection():
    """Tamper with a signed WAL entry and verify signature failure."""
    print("  Test 4: Signed WAL tamper detection")

    with tempfile.TemporaryDirectory(prefix="gate8_sigtamper_") as tmpdir:
        signer = Ed25519WALSigner.generate()
        eid = "sigtamper-001"

        with WALWriter(tmpdir, eid, signer=signer) as wal:
            wal.execution_started(envelope_hash="env_hash_004", intent_name="test.sigtamper")
            wal.step_started(
                step_id="s1", agent_name="agent-a",
                side_effect="none", contracts={}, input_hash="in1",
            )
            wal.step_completed(step_id="s1", output_hash="out1", success=True)

        reader = WALReader(tmpdir, eid)
        entries = reader.read_all(verify_integrity=True)

        verifier = Ed25519WALVerifier()
        verifier.add_from_signer(signer)

        # Tamper with payload and recompute hash but DON'T re-sign
        tampered = entries[-1]
        tampered.payload["success"] = False
        tampered.entry_hash = tampered.compute_hash()

        valid = tampered.verify_signature(verifier)
        if valid:
            print("    FAIL: Tampered entry should have INVALID signature")
            return False

        print("    Tampered entry correctly rejected — signature invalid")
        return True


def main():
    print("Gate 8: WAL Integrity & Tamper Detection")
    print("=" * 50)

    results = [
        test_hash_chain_integrity(),
        test_tamper_detection(),
        test_signed_wal_valid(),
        test_signed_tamper_detection(),
    ]

    print()
    passed = sum(results)
    total = len(results)
    print(f"  Results: {passed}/{total} tests passed")

    if not all(results):
        print()
        print("  GATE 8 FAIL: WAL integrity or tamper detection broken")
        sys.exit(1)

    print()
    print("  GATE 8 PASS: WAL integrity and tamper detection verified")


if __name__ == "__main__":
    main()
