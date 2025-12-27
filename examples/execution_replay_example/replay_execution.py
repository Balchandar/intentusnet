from intentusnet.recording.store import FileExecutionStore
from intentusnet.recording.replay import ReplayEngine


RECORD_DIR = "examples/execution_replay_example/records"
COORDINATOR_INTENT = "support.ticket.analyze"


def main():
    store = FileExecutionStore(RECORD_DIR)

    execution_ids = store.list_ids()
    if not execution_ids:
        raise RuntimeError("No execution records found")

    # Load all records
    records = [store.load(eid) for eid in execution_ids]

    # Filter coordinator executions
    coordinator_records = [
        r for r in records
        if r.envelope.get("intent", {}).get("name") == COORDINATOR_INTENT
    ]

    if not coordinator_records:
        raise RuntimeError(
            f"No execution record found for intent '{COORDINATOR_INTENT}'"
        )

    # Pick the most recent coordinator execution
    coordinator_records.sort(
        key=lambda r: r.header.createdUtcIso
    )
    latest_record = coordinator_records[-1]

    # Replay
    engine = ReplayEngine(latest_record)
    result = engine.replay()

    print("Replayed response:", result.response["payload"])
    print("Envelope hash match:", result.envelope_hash_ok)


if __name__ == "__main__":
    main()
