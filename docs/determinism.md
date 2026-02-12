# Provable Determinism

## Overview

IntentusNet v4.5 treats determinism as a **provable property**, not just a design goal. The runtime includes built-in mechanisms to verify, enforce, and prove that execution behavior is deterministic across runs, environments, and model swaps.

This document covers:

1. Execution fingerprinting
2. Replay guarantee
3. Drift detection
4. Deterministic-safe CI/CD enforcement

---

## Execution Fingerprinting

Every execution produces a **SHA-256 fingerprint** — a cryptographic hash of the execution's deterministic properties.

### What's Included in the Fingerprint

| Component | Description |
|-----------|-------------|
| Intent sequence | Ordered list of intents processed |
| Tool/agent call sequence | Which agents were called, in what order |
| Parameter hashes | SHA-256 of each input parameter set |
| Output hashes | SHA-256 of each agent response |
| Retry pattern | Which agents were retried and how many times |
| Execution order | The exact sequence of routing decisions |
| Timeout values | Configured timeouts that affect execution paths |

### The Determinism Equation

```
Same input + Same runtime configuration = Same fingerprint
```

If the fingerprint changes between two runs with identical input, something in the execution path is nondeterministic. The system detects this automatically.

### How Fingerprints Are Computed

```python
fingerprint_data = {
    "intent_sequence": [hash(intent) for intent in intents],
    "tool_sequence": [agent.name for agent in executed_agents],
    "param_hashes": [hash(params) for params in all_params],
    "output_hashes": [hash(output) for output in all_outputs],
    "retry_pattern": retry_counts,
    "execution_order": routing_decisions,
    "timeout_values": configured_timeouts,
}
fingerprint = sha256(canonical_json(fingerprint_data))
```

### What's Excluded from the Fingerprint

- Wall-clock timestamps (nondeterministic by nature)
- Execution IDs (UUIDs, used for identification only)
- Log messages
- Metrics and observability data

---

## Replay Guarantee

IntentusNet guarantees that stored responses can be retrieved **without re-executing any agent code**.

### How It Works

1. **Record**: During execution, the runtime records the full execution state — including the final response, routing decisions, and agent outputs.
2. **Store**: The execution record is persisted as an immutable artifact with a stable content hash.
3. **Retrieve**: The `HistoricalResponseEngine` returns the stored response directly. No agent code runs. No model is called.

### Verification

Replay verification proves that the stored response matches the original execution:

```python
# Original execution
original = runtime.send_intent("assess_risk", payload)
original_hash = hash(original.response)

# Replay (no model, no agent code)
replayed = historical_engine.retrieve(original.execution_id)
replay_hash = hash(replayed.response)

assert original_hash == replay_hash  # Always true
```

This is not a test — it is a **structural guarantee** of the recording system.

---

## Drift Detection

Drift detection identifies when execution behavior becomes nondeterministic.

### How It Works

1. Run the same intent N times with identical input
2. Compute the execution fingerprint for each run
3. Compare all N fingerprints
4. If any fingerprint differs → **drift detected**

### What Causes Drift

| Source | Example | Detection |
|--------|---------|-----------|
| Unseeded randomness | `random.random()` in agent logic | Fingerprint mismatch |
| Time-dependent logic | `datetime.now()` in routing decisions | Fingerprint mismatch |
| External state | Database reads that change between runs | Output hash mismatch |
| Nondeterministic iteration | `dict` ordering in Python < 3.7 | Execution order mismatch |

### What Drift Detection Does NOT Catch

- Model nondeterminism (different LLM outputs for same prompt) — this is expected and recorded, not blocked
- External service variability — recorded but not controlled by the runtime

### CI Gate: Entropy Detection

The entropy detection gate performs **static analysis** on deterministic-critical code paths, scanning for:

| Pattern | Risk |
|---------|------|
| `random.random()` / `random.randint()` without seed | Unseeded randomness |
| `uuid.uuid4()` in step ID or fingerprint computation | Nondeterministic identifiers in deterministic paths |
| `time.time()` / `datetime.now()` in hash computation | Time-dependent hashes |
| `os.urandom()` in hash computation | Cryptographic randomness in deterministic paths |

Known-safe uses (e.g., `uuid4()` for execution IDs, which are excluded from fingerprints) are allowlisted.

---

## Deterministic-Safe CI/CD

The CI/CD pipeline enforces determinism through **9 verification gates**. All gates must pass before deployment.

See [ci-cd.md](ci-cd.md) for the complete gate specification.

### Gate Summary

| # | Gate | What It Proves |
|---|------|---------------|
| 1 | Build Reproducibility | Same source → same binary |
| 2 | Deterministic Execution | Same input → same fingerprint |
| 3 | WAL Replay Final-State | Stored response matches original |
| 4 | Entropy Detection | No unseeded randomness in critical paths |
| 5 | Container Reproducibility | Same Dockerfile → same image hash |
| 6 | Routing Determinism | Same capabilities → same agent selection |
| 7 | Crash Recovery | Safe resume/block based on side-effect class |
| 8 | WAL Integrity & Tamper | Hash chain intact, tampering detected |
| 9 | Runtime Snapshot | Execution record survives serialization round-trip |

### Enforcement Model

- **Pre-deployment**: All 9 gates run on every commit
- **Blocking**: A single gate failure blocks the release
- **Non-bypassable**: Gates cannot be skipped or overridden without explicit configuration change

---

## Determinism Boundary

Determinism is enforced at the **execution layer**, not the model layer.

### What Is Deterministic

- Agent selection (routing)
- Fallback chains
- Retry behavior
- Side-effect classification
- Contract enforcement
- Execution recording
- Fingerprint computation

### What Is NOT Deterministic (By Design)

- LLM model outputs (different for same prompt across calls)
- External API responses
- Network latency

These nondeterministic inputs are **recorded** so they can be inspected, but the runtime does not attempt to make them deterministic. The execution path around them remains deterministic.

---

## References

- [CI/CD Gate Specification](ci-cd.md)
- [WAL Format](wal-format.md)
- [Runtime Determinism Core](runtime-determinism.md)
- [Release Notes v4.5](release-notes/v4.5.md)
