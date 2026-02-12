"""
Test suite for ExecutionHeader.replayableReason field (Improvement #2).

Verifies that the missing field has been added and works correctly.
"""

import pytest
from intentusnet.recording.models import ExecutionHeader, ExecutionRecord
from intentusnet.recording.recorder import InMemoryExecutionRecorder


def test_replayable_reason_field_exists():
    """Verify replayableReason field can be set."""
    header = ExecutionHeader(
        executionId="test-123",
        createdUtcIso="2026-01-02T00:00:00Z",
        envelopeHash="abc123def456",
        replayable=False,
        replayableReason="Test marked non-replayable",
    )

    assert header.replayableReason == "Test marked non-replayable"
    assert header.replayable is False


def test_replayable_reason_defaults_to_none():
    """Verify replayableReason has correct default."""
    header = ExecutionHeader(
        executionId="test-123",
        createdUtcIso="2026-01-02T00:00:00Z",
        envelopeHash="abc123def456",
    )

    assert header.replayableReason is None
    assert header.replayable is True  # Default


def test_mark_not_replayable():
    """
    Integration test: mark_not_replayable sets reason.

    Bug: Before fix, this would raise AttributeError because
    replayableReason field didn't exist in ExecutionHeader.
    """
    record = ExecutionRecord.new(
        execution_id="test-456",
        created_utc_iso="2026-01-02T00:00:00Z",
        env={"test": "envelope"},
    )

    recorder = InMemoryExecutionRecorder(record)
    recorder.mark_not_replayable("External API call")

    assert recorder.get_record().header.replayable is False
    assert recorder.get_record().header.replayableReason == "External API call"


def test_execution_header_serialization():
    """Verify to_dict includes replayableReason."""
    record = ExecutionRecord.new(
        execution_id="test-789",
        created_utc_iso="2026-01-02T00:00:00Z",
        env={"test": "data"},
        replayable=False,
    )

    # Manually set replayableReason
    record.header.replayableReason = "Model called external API"

    record_dict = record.to_dict()

    assert record_dict["header"]["replayableReason"] == "Model called external API"
    assert record_dict["header"]["replayable"] is False


def test_execution_header_deserialization():
    """Verify from_dict loads replayableReason."""
    data = {
        "header": {
            "executionId": "test-abc",
            "createdUtcIso": "2026-01-02T00:00:00Z",
            "envelopeHash": "hash123",
            "replayable": False,
            "replayableReason": "Non-deterministic operation",
        },
        "envelope": {"test": "data"},
        "routerDecision": None,
        "events": [],
        "finalResponse": None,
    }

    record = ExecutionRecord.from_dict(data)

    assert record.header.replayableReason == "Non-deterministic operation"
    assert record.header.replayable is False


def test_backward_compatibility_missing_reason():
    """
    Verify from_dict handles old records without replayableReason.

    Old execution records won't have this field, so it should
    default to None.
    """
    data = {
        "header": {
            "executionId": "old-record",
            "createdUtcIso": "2025-12-01T00:00:00Z",
            "envelopeHash": "oldhash",
            "replayable": True,
            # ❌ Missing replayableReason
        },
        "envelope": {"old": "data"},
        "routerDecision": None,
        "events": [],
        "finalResponse": None,
    }

    record = ExecutionRecord.from_dict(data)

    assert record.header.replayableReason is None
    assert record.header.replayable is True


def test_replay_engine_uses_replayable_reason():
    """Verify ReplayEngine includes reason in error messages."""
    from intentusnet.recording.replay import ReplayEngine, ReplayError

    record = ExecutionRecord.new(
        execution_id="test-fail",
        created_utc_iso="2026-01-02T00:00:00Z",
        env={"test": "data"},
        replayable=False,
    )
    record.header.replayableReason = "Contains external API calls"

    engine = ReplayEngine(record)
    ok, reason = engine.is_replayable()

    assert ok is False
    assert reason == "Contains external API calls"


def test_replay_engine_handles_missing_reason():
    """Verify ReplayEngine handles missing reason gracefully."""
    from intentusnet.recording.replay import ReplayEngine

    record = ExecutionRecord.new(
        execution_id="test-no-reason",
        created_utc_iso="2026-01-02T00:00:00Z",
        env={"test": "data"},
        replayable=False,
    )
    # Don't set replayableReason

    engine = ReplayEngine(record)
    ok, reason = engine.is_replayable()

    assert ok is False
    assert "Marked not retrievable" in reason


def test_round_trip_with_replayable_reason():
    """End-to-end test: create → serialize → deserialize → verify."""
    original = ExecutionRecord.new(
        execution_id="round-trip-test",
        created_utc_iso="2026-01-02T12:00:00Z",
        env={"intent": "TestIntent", "payload": {"key": "value"}},
        replayable=False,
    )
    original.header.replayableReason = "Used random number generator"

    # Serialize
    data = original.to_dict()

    # Deserialize
    restored = ExecutionRecord.from_dict(data)

    assert restored.header.executionId == "round-trip-test"
    assert restored.header.replayable is False
    assert restored.header.replayableReason == "Used random number generator"
    assert restored.envelope == {"intent": "TestIntent", "payload": {"key": "value"}}
