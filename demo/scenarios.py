"""Four-act demo scenarios stitched from existing IntentusNet primitives.
No core logic re-implemented — only narrative wiring."""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from intentusnet.recording.models import (
    ExecutionEvent, ExecutionHeader, ExecutionRecord, stable_hash,
)
from intentusnet.recording.store import FileExecutionStore
from intentusnet.security.capability_governor_v2 import CapabilityGovernor
from intentusnet.security.causality_index import CausalityIndex, ExecutionNode
from intentusnet.security.circuit_breaker_v2 import CircuitBreaker
from intentusnet.security.event_bus import SecurityEventBus, SecurityEventType
from intentusnet.security.replay_engine import (
    ReplayComparisonResult, SecurityReplayEngine,
)
from intentusnet.security.signals import DecomposedSignalSet, compute as compute_signals
from intentusnet.security.types import ReplayMode
from intentusnet.wal.writer import WALWriter

from .mock_agents import MockLLMAgent, MockToolAgent, baseline_run, intentus_run


GREEN, RED, YELLOW, CYAN = "\033[92m", "\033[91m", "\033[93m", "\033[96m"
DIM, BOLD, RESET = "\033[2m", "\033[1m", "\033[0m"


def _banner(title: str) -> None:
    line = "=" * 70
    print(f"\n{BOLD}{CYAN}{line}\n{title.center(70)}\n{line}{RESET}")


def _section(title: str) -> None:
    print(f"\n{BOLD}--- {title} ---{RESET}")


def _kv(key: str, value: Any) -> None:
    print(f"  {DIM}{key:<22}{RESET} {value}")


def _bar(value: float, *, width: int = 24) -> str:
    filled = max(0, min(width, int(round(value * width))))
    return "█" * filled + "·" * (width - filled)


@dataclass
class DemoArtifacts:
    record_dir: str
    wal_dir: str
    execution_id: str
    record_path: str
    wal_path: str
    event_log: List[Dict[str, Any]] = field(default_factory=list)


# Act 1 — Baseline ----------------------------------------------------------


def act1_baseline(prompt: str) -> Dict[str, Any]:
    _banner("=== BASELINE EXECUTION ===")
    print(f"{DIM}Running the workload directly: model → tool → answer.\n"
          f"No execution trace, no signals, no replay capability.{RESET}")

    t0 = time.perf_counter()
    result = baseline_run(MockLLMAgent(), MockToolAgent(), prompt)
    wall_ms = (time.perf_counter() - t0) * 1000.0

    _section("Baseline output")
    _kv("prompt", prompt)
    _kv("answer", result["summary"])
    _kv("wall_time_ms", f"{wall_ms:.2f}")
    print(f"{YELLOW}[!] Without IntentusNet there is nothing to inspect.\n"
          f"[!] If the tool silently changed, no one would know.{RESET}")
    return {"result": result, "wall_ms": wall_ms}


# Act 2 — IntentusNet -------------------------------------------------------


def act2_intentus(
    prompt: str, *, record_dir: str, wal_dir: str,
    intent_name: str = "summarize_complaints",
    tool_latency_override_ms: Optional[float] = None,
    induce_failure: bool = False,
) -> DemoArtifacts:
    _banner("=== INTENTUSNET EXECUTION ===")
    print(f"{DIM}Same workload, now wrapped in the Intent Kernel.\n"
          f"Every step is traced, scored, and recorded to disk.{RESET}")

    bus = SecurityEventBus(max_queue=1024)
    event_sink: List[Dict[str, Any]] = []
    bus.subscribe("demo-collector", lambda ev: event_sink.append(ev.to_dict()))

    breaker = CircuitBreaker(failure_threshold=3, timeout_seconds=2.0, event_bus=bus)
    governor = CapabilityGovernor(behavior_threshold=0.85, event_bus=bus)
    causality = CausalityIndex(segment_size=64)

    execution_id = str(uuid.uuid4())
    envelope = {
        "intent": intent_name, "intent_name": intent_name,
        "prompt": prompt, "version": "1.0",
    }

    causality.add_node(ExecutionNode(
        execution_id=execution_id, agent_id=intent_name,
        step_seq=0, depth=0, metadata={"prompt": prompt},
    ))

    if not breaker.allow(intent_name):
        bus.stop()
        raise RuntimeError("circuit breaker open")
    bus.emit(
        SecurityEventType.EXECUTION_STARTED, intent_name,
        execution_id=execution_id, payload={"prompt_len": len(prompt)},
    )

    llm = MockLLMAgent()
    tool = MockToolAgent(
        latency_override_ms=tool_latency_override_ms, fail_next=induce_failure,
    )

    t0 = time.perf_counter()
    run = intentus_run(llm, tool, prompt)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    success = run["error"] is None

    causality.add_node(ExecutionNode(
        execution_id=stable_hash(f"{execution_id}:tool:{intent_name}"),
        agent_id="complaints_db", step_seq=1, depth=1,
        parent_id=execution_id, metadata={"action": "query"},
    ))

    signals: DecomposedSignalSet = compute_signals(
        intent_name, latency_ms=latency_ms,
        error_occurred=not success, consecutive_errors=0 if success else 1,
    )

    new_state = breaker.record(intent_name, signals, success=success)
    governor.record(intent_name, signals.behavior_signal)

    bus.emit(
        SecurityEventType.EXECUTION_COMPLETED if success
        else SecurityEventType.EXECUTION_FAILED,
        intent_name, execution_id=execution_id,
        payload={
            "latency_ms": round(latency_ms, 2),
            "signals": signals.to_dict(),
            "circuit_state": new_state.value,
        },
    )

    os.makedirs(record_dir, exist_ok=True)
    record = ExecutionRecord(
        header=ExecutionHeader(
            executionId=execution_id,
            createdUtcIso=datetime.now(timezone.utc).isoformat(),
            envelopeHash=stable_hash(envelope), replayable=True,
        ),
        envelope=envelope,
        routerDecision={"selected_agent": llm.name, "tool": "complaints_db"},
        events=[ExecutionEvent(seq=s["seq"], type=s["actor"], payload=s)
                for s in run["steps"]],
        finalResponse=run["tool_response"] if success else {"error": run["error"]},
    )
    record_path = FileExecutionStore(record_dir).save(record)

    os.makedirs(wal_dir, exist_ok=True)
    wal_path = os.path.join(wal_dir, f"{execution_id}.wal")
    with WALWriter(wal_dir, execution_id) as wal:
        wal.execution_started(envelope_hash=record.header.envelopeHash, intent_name=intent_name)
        for step in run["steps"]:
            sid = f"step-{step['seq']:03d}"
            payload_hash = stable_hash(step["payload"])
            wal.step_started(
                step_id=sid, agent_name=step["actor"],
                side_effect="read_only", contracts={}, input_hash=payload_hash,
            )
            wal.step_completed(
                step_id=sid, output_hash=payload_hash, success=step["error"] is None,
            )
        if success:
            wal.execution_completed(response_hash=stable_hash(record.finalResponse))
        else:
            wal.execution_failed(
                failure_type="tool_error",
                reason=run["error"] or "unknown", recoverable=True,
            )

    _section("Execution trace (intent → agent → tool)")
    for s in run["steps"]:
        marker = f"{RED}✗{RESET}" if s["error"] else f"{GREEN}✓{RESET}"
        print(f"  {marker} seq={s['seq']:>2}  {s['actor']:<14} "
              f"{s['action']:<10}  latency={s['latency_ms']:>6.2f} ms")

    _section("Decomposed signals (independent channels)")
    for k, v in signals.to_dict().items():
        _kv(k, f"{v:.4f}  {_bar(v)}")

    _section("Enforcement snapshot")
    _kv("circuit_state", new_state.value)
    _kv("intent_allowed", governor.is_allowed(intent_name))
    _kv("event_bus_drops", bus.dropped_events)

    _section("Persistence")
    _kv("execution_id", execution_id)
    _kv("record_path", record_path)
    _kv("wal_path", wal_path)

    time.sleep(0.05)
    bus.stop()

    _section("Security events (bus)")
    for ev in event_sink:
        print(f"  {DIM}lc={ev['lamport_clock']:>3} "
              f"{ev['event_type']:<24} intent={ev['intent_name']}{RESET}")

    return DemoArtifacts(
        record_dir=record_dir, wal_dir=wal_dir,
        execution_id=execution_id, record_path=record_path,
        wal_path=wal_path, event_log=event_sink,
    )


# Act 3 — Replay (MATCH) ----------------------------------------------------


def act3_replay_match(artifacts: DemoArtifacts) -> ReplayComparisonResult:
    _banner("=== REPLAY (EXPECT MATCH) ===")
    print(f"{DIM}Re-running the same intent against the same mock agents.\n"
          f"The replay engine compares stable hashes — order/precision noise\n"
          f"is normalised away by canonical JSON.{RESET}")

    record = FileExecutionStore(artifacts.record_dir).load(artifacts.execution_id)
    engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
    llm, tool = MockLLMAgent(), MockToolAgent()
    prompt = record.envelope.get("prompt", "")

    result = engine.execute(record, lambda: baseline_run(llm, tool, prompt)["tool_response"])

    _section("Replay result")
    _kv("execution_id", result.execution_id)
    _kv("original_hash", result.original_hash[:24] + "…")
    _kv("replay_hash", result.replay_hash[:24] + "…")
    _kv("wall_seconds", f"{result.wall_seconds:.4f}")
    print(f"{GREEN}{BOLD}Replay Status: MATCH ✅{RESET}" if result.matched
          else f"{RED}{BOLD}Replay Status: UNEXPECTED MISMATCH ❌{RESET}")
    return result


# Act 4 — Divergence --------------------------------------------------------


def act4_replay_divergence(artifacts: DemoArtifacts) -> Dict[str, Any]:
    _banner("=== REPLAY AFTER MUTATION (EXPECT DIVERGENCE) ===")
    print(f"{DIM}A bug ships. The tool now returns total=95 instead of 120.\n"
          f"The replay engine notices because the recorded hash no longer\n"
          f"matches the new response.{RESET}")

    record = FileExecutionStore(artifacts.record_dir).load(artifacts.execution_id)
    engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
    llm = MockLLMAgent()
    tool = MockToolAgent(mutation=lambda r: {**r, "total": 95})
    prompt = record.envelope.get("prompt", "")

    def _replay():
        return baseline_run(llm, tool, prompt)["tool_response"]

    result = engine.execute(record, _replay)
    new_response = _replay()
    diff = _diff_payload(record.finalResponse, new_response)

    _section("Replay result")
    _kv("execution_id", result.execution_id)
    _kv("matched", result.matched)
    _kv("original_hash", result.original_hash[:24] + "…")
    _kv("replay_hash", result.replay_hash[:24] + "…")

    _section("Field-level diff")
    if not diff:
        print(f"{YELLOW}  (no scalar diffs — structure changed){RESET}")
    for path, (old, new) in diff.items():
        print(f"  {RED}- {path:<28}{RESET} original={old}   "
              f"{GREEN}replay={new}{RESET}")

    print(f"{RED}{BOLD}Replay Status: DIVERGENCE DETECTED ❌{RESET}" if not result.matched
          else f"{YELLOW}{BOLD}Unexpected: replay still matched.{RESET}")
    return {"result": result, "diff": diff, "new_response": new_response}


def _diff_payload(old: Any, new: Any, *, path: str = "") -> Dict[str, Tuple[Any, Any]]:
    out: Dict[str, Tuple[Any, Any]] = {}
    if type(old) is not type(new):
        out[path or "<root>"] = (old, new)
        return out
    if isinstance(old, dict):
        for k in sorted(set(old.keys()) | set(new.keys())):
            out.update(_diff_payload(old.get(k), new.get(k),
                                     path=f"{path}.{k}" if path else k))
        return out
    if isinstance(old, list):
        if len(old) != len(new):
            out[path or "<root>"] = (old, new)
            return out
        for i, (a, b) in enumerate(zip(old, new)):
            out.update(_diff_payload(a, b, path=f"{path}[{i}]"))
        return out
    if old != new:
        out[path or "<root>"] = (old, new)
    return out
