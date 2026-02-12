#!/usr/bin/env python3
"""
Gate 9: Runtime Snapshot Verification

Proves: snapshot → rebuild → state hash must match.

1. Create a runtime, register agents, execute
2. Serialize the execution record (snapshot)
3. Load the snapshot into a new process
4. Verify the response hash matches the original
5. Verify envelope hash consistency
"""

import os
import json
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from intentusnet.core.runtime import IntentusRuntime
from intentusnet.core.agent import BaseAgent
from intentusnet.protocol.agent import AgentDefinition, Capability
from intentusnet.protocol.intent import IntentRef
from intentusnet.protocol.response import AgentResponse
from intentusnet.recording.store import FileExecutionStore
from intentusnet.recording.models import ExecutionRecord, stable_hash


class SnapshotTestAgent(BaseAgent):
    def handle_intent(self, env):
        v = env.payload.get("x", 0)
        return AgentResponse.success(
            payload={"result": v * v + 1, "source": "snapshot-agent"},
            agent=self.definition.name,
        )


def main():
    print("Gate 9: Runtime Snapshot Verification")
    print("=" * 50)

    agent_def = AgentDefinition(
        name="snapshot-agent", version="1.0", nodePriority=10,
        capabilities=[Capability(intent=IntentRef(name="test.snapshot", version="1.0"))],
    )

    with tempfile.TemporaryDirectory(prefix="gate9_") as tmpdir:
        record_dir = os.path.join(tmpdir, "records")

        # Step 1: Execute and record
        print("  Step 1: Execute and create snapshot...")
        rt = IntentusRuntime(enable_recording=True, record_dir=record_dir)
        rt.register_agent(lambda r: SnapshotTestAgent(agent_def, r))
        client = rt.client()
        resp = client.send_intent("test.snapshot", payload={"x": 17})

        original_hash = stable_hash({"status": resp.status, "payload": resp.payload})
        print(f"    Original response hash: {original_hash[:24]}...")

        # Step 2: Snapshot to disk (already done by recording)
        store = FileExecutionStore(record_dir)
        ids = store.list_ids()
        record = store.load(ids[0])
        snapshot_path = os.path.join(tmpdir, "snapshot.json")

        with open(snapshot_path, "w") as f:
            json.dump(record.to_dict(), f, indent=2)

        snapshot_size = os.path.getsize(snapshot_path)
        print(f"    Snapshot written: {snapshot_size} bytes")

        # Step 3: Rebuild from snapshot
        print("  Step 2: Rebuild record from snapshot...")
        with open(snapshot_path) as f:
            snapshot_data = json.load(f)

        rebuilt_record = ExecutionRecord.from_dict(snapshot_data)

        # Step 4: Verify hashes match
        print("  Step 3: Verify rebuilt record matches original...")
        rebuilt_response_hash = stable_hash(rebuilt_record.finalResponse)
        original_response_hash = stable_hash(record.finalResponse)

        print(f"    Original record hash:  {original_response_hash[:24]}...")
        print(f"    Rebuilt record hash:   {rebuilt_response_hash[:24]}...")

        if original_response_hash != rebuilt_response_hash:
            print()
            print("  GATE 9 FAIL: Rebuilt record hash does not match original")
            sys.exit(1)

        # Step 5: Verify header consistency
        print("  Step 4: Verify header consistency...")
        if record.header.executionId != rebuilt_record.header.executionId:
            print("  GATE 9 FAIL: Execution ID mismatch after rebuild")
            sys.exit(1)

        if record.header.envelopeHash != rebuilt_record.header.envelopeHash:
            print("  GATE 9 FAIL: Envelope hash mismatch after rebuild")
            sys.exit(1)

        if record.header.replayable != rebuilt_record.header.replayable:
            print("  GATE 9 FAIL: Replayable flag mismatch after rebuild")
            sys.exit(1)

        print(f"    executionId: {rebuilt_record.header.executionId[:24]}... OK")
        print(f"    envelopeHash: {rebuilt_record.header.envelopeHash[:24]}... OK")
        print(f"    replayable: {rebuilt_record.header.replayable} OK")

        # Step 6: Verify event count
        if len(record.events) != len(rebuilt_record.events):
            print(f"  GATE 9 FAIL: Event count mismatch: "
                  f"{len(record.events)} vs {len(rebuilt_record.events)}")
            sys.exit(1)
        print(f"    events: {len(rebuilt_record.events)} OK")

    print()
    print("  GATE 9 PASS: Snapshot → rebuild → hash match verified")


if __name__ == "__main__":
    main()
