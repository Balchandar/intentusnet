"""Integration tests for the divergence path.

Each test records a normal run, then either mutates the tool response or
substitutes a different model plan and asserts the production replay
engine flags the divergence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from demo.mock_agents import MockLLMAgent, MockToolAgent, baseline_run
from demo.scenarios import _diff_payload, act2_intentus

from intentusnet.recording.store import FileExecutionStore
from intentusnet.security.event_bus import (
    SecurityEvent,
    SecurityEventBus,
    SecurityEventType,
)
from intentusnet.security.replay_engine import (
    ReplayDivergenceError,
    SecurityReplayEngine,
)
from intentusnet.security.types import ReplayMode


@pytest.fixture
def demo_dirs(tmp_path: Path) -> tuple[str, str]:
    record_dir = tmp_path / "records"
    wal_dir = tmp_path / "wal"
    record_dir.mkdir()
    wal_dir.mkdir()
    return str(record_dir), str(wal_dir)


def _record_one(record_dir: str, wal_dir: str) -> str:
    artifacts = act2_intentus(
        "divergence test prompt",
        record_dir=record_dir,
        wal_dir=wal_dir,
        intent_name="test_divergence",
    )
    return artifacts.execution_id


def test_mutated_tool_response_diverges(demo_dirs):
    record_dir, wal_dir = demo_dirs
    eid = _record_one(record_dir, wal_dir)

    store = FileExecutionStore(record_dir)
    record = store.load(eid)

    # Replace one field in the tool response.
    tool = MockToolAgent(mutation=lambda r: {**r, "total": 95})
    llm = MockLLMAgent()
    prompt = record.envelope["prompt"]

    engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
    result = engine.execute(
        record, lambda: baseline_run(llm, tool, prompt)["tool_response"]
    )

    assert result.matched is False
    assert result.original_hash != result.replay_hash


def test_diff_pinpoints_mutated_field(demo_dirs):
    record_dir, wal_dir = demo_dirs
    eid = _record_one(record_dir, wal_dir)

    store = FileExecutionStore(record_dir)
    record = store.load(eid)

    tool = MockToolAgent(mutation=lambda r: {**r, "total": 95})
    new_response = baseline_run(MockLLMAgent(), tool, record.envelope["prompt"])[
        "tool_response"
    ]

    diff = _diff_payload(record.finalResponse, new_response)
    # Only the mutated field should appear in the diff.
    assert "total" in diff
    old, new = diff["total"]
    assert old == 120
    assert new == 95


def test_enforce_mode_raises_on_divergence(demo_dirs):
    """In ENFORCE mode the replay engine must raise rather than return."""
    record_dir, wal_dir = demo_dirs
    eid = _record_one(record_dir, wal_dir)

    store = FileExecutionStore(record_dir)
    record = store.load(eid)

    tool = MockToolAgent(mutation=lambda r: {**r, "top_issue": "data export"})
    llm = MockLLMAgent()
    prompt = record.envelope["prompt"]

    engine = SecurityReplayEngine(mode=ReplayMode.ENFORCE)
    with pytest.raises(ReplayDivergenceError) as excinfo:
        engine.execute(record, lambda: baseline_run(llm, tool, prompt)["tool_response"])

    assert excinfo.value.result.matched is False
    assert excinfo.value.result.execution_id == eid


def test_divergence_emits_replay_event(demo_dirs):
    """Divergence in SHADOW mode must emit ``REPLAY_DIVERGENCE`` on the bus."""
    record_dir, wal_dir = demo_dirs
    eid = _record_one(record_dir, wal_dir)

    store = FileExecutionStore(record_dir)
    record = store.load(eid)

    bus = SecurityEventBus(max_queue=64)
    captured: list[SecurityEvent] = []
    bus.subscribe("test-collector", lambda ev: captured.append(ev))

    engine = SecurityReplayEngine(mode=ReplayMode.SHADOW, event_bus=bus)

    tool = MockToolAgent(mutation=lambda r: {**r, "count": 999})
    llm = MockLLMAgent()
    prompt = record.envelope["prompt"]
    engine.execute(record, lambda: baseline_run(llm, tool, prompt)["tool_response"])

    # Drain the bus.
    import time

    time.sleep(0.1)
    bus.stop()

    types = [ev.event_type for ev in captured]
    assert SecurityEventType.REPLAY_DIVERGENCE in types


def test_unmutated_replay_does_not_emit_divergence(demo_dirs):
    """Negative control: the same recording must replay clean against an
    unmutated tool."""
    record_dir, wal_dir = demo_dirs
    eid = _record_one(record_dir, wal_dir)

    store = FileExecutionStore(record_dir)
    record = store.load(eid)

    bus = SecurityEventBus(max_queue=64)
    captured: list[SecurityEvent] = []
    bus.subscribe("ctl-collector", lambda ev: captured.append(ev))

    engine = SecurityReplayEngine(mode=ReplayMode.SHADOW, event_bus=bus)

    llm = MockLLMAgent()
    tool = MockToolAgent()
    prompt = record.envelope["prompt"]
    result = engine.execute(record, lambda: baseline_run(llm, tool, prompt)["tool_response"])

    import time

    time.sleep(0.1)
    bus.stop()

    assert result.matched is True
    types = [ev.event_type for ev in captured]
    assert SecurityEventType.REPLAY_DIVERGENCE not in types
