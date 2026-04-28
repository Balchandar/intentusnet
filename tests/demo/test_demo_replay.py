"""Integration tests for the demo's record-then-replay path.

Asserts that a fresh execution recorded via :func:`demo.scenarios.act2_intentus`
can be replayed by the production
:class:`intentusnet.security.replay_engine.SecurityReplayEngine` and that the
replay engine returns ``matched=True``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from demo.mock_agents import MockLLMAgent, MockToolAgent, baseline_run
from demo.scenarios import act2_intentus

from intentusnet.recording.store import FileExecutionStore
from intentusnet.security.replay_engine import SecurityReplayEngine
from intentusnet.security.types import ReplayMode
from intentusnet.wal.integrity import verify_wal_integrity


@pytest.fixture
def demo_dirs(tmp_path: Path) -> tuple[str, str]:
    """Per-test record + WAL directories under pytest's tmp_path."""
    record_dir = tmp_path / "records"
    wal_dir = tmp_path / "wal"
    record_dir.mkdir()
    wal_dir.mkdir()
    return str(record_dir), str(wal_dir)


def test_recorded_execution_replays_and_matches(demo_dirs):
    """Round-trip: record → load → replay → match."""
    record_dir, wal_dir = demo_dirs

    artifacts = act2_intentus(
        "Summarize last month's complaints",
        record_dir=record_dir,
        wal_dir=wal_dir,
        intent_name="test_summarize",
    )

    store = FileExecutionStore(record_dir)
    record = store.load(artifacts.execution_id)
    assert record.header.executionId == artifacts.execution_id
    assert record.is_replayable()

    engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)

    llm = MockLLMAgent()
    tool = MockToolAgent()
    prompt = record.envelope["prompt"]

    def _replay():
        return baseline_run(llm, tool, prompt)["tool_response"]

    result = engine.execute(record, _replay)
    assert result.matched is True
    assert result.original_hash == result.replay_hash
    assert result.execution_id == artifacts.execution_id


def test_wal_chain_is_intact_for_recorded_execution(demo_dirs):
    """The WAL written during act2 must verify cleanly."""
    record_dir, wal_dir = demo_dirs

    artifacts = act2_intentus(
        "trace integrity prompt",
        record_dir=record_dir,
        wal_dir=wal_dir,
        intent_name="test_chain",
    )

    integrity = verify_wal_integrity(wal_dir, artifacts.execution_id)
    assert integrity.ok is True
    assert integrity.entry_count >= 4   # started + at least one step + completed
    assert integrity.first_hash is not None
    assert integrity.last_hash is not None
    assert integrity.errors == []


def test_replay_is_deterministic_across_repeated_runs(demo_dirs):
    """Calling the replay engine twice must produce identical hashes."""
    record_dir, wal_dir = demo_dirs

    artifacts = act2_intentus(
        "deterministic check",
        record_dir=record_dir,
        wal_dir=wal_dir,
        intent_name="test_deterministic",
    )

    store = FileExecutionStore(record_dir)
    record = store.load(artifacts.execution_id)
    engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)

    def _replay():
        return baseline_run(MockLLMAgent(), MockToolAgent(), record.envelope["prompt"])[
            "tool_response"
        ]

    r1 = engine.execute(record, _replay)
    r2 = engine.execute(record, _replay)
    assert r1.replay_hash == r2.replay_hash
    assert r1.matched and r2.matched
