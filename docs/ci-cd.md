# Deterministic-Safe CI/CD

## Overview

IntentusNet v1.5.1 includes a **9-gate CI/CD verification pipeline** that enforces determinism before deployment. This is not a test suite — it is a deployment gate. Every gate must pass, or the release is blocked.

The pipeline is defined in `.github/workflows/deterministic-stability.yml`.

---

## Gate Architecture

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   Gate 1    │  │   Gate 2    │  │   Gate 3    │
│   Build     │  │ Determinism │  │ WAL Replay  │
│   Repro     │  │  Execution  │  │ Final-State │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐
│   Gate 4    │  │   Gate 5    │  │   Gate 6    │
│  Entropy    │  │ Container   │  │  Routing    │
│ Detection   │  │   Repro     │  │ Determinism │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐
│   Gate 7    │  │   Gate 8    │  │   Gate 9    │
│   Crash     │  │    WAL      │  │  Runtime    │
│  Recovery   │  │ Integrity   │  │  Snapshot   │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       └────────────────┼────────────────┘
                        │
               ┌────────┴────────┐
               │  Deploy Gate    │
               │  (All 9 pass)   │
               └─────────────────┘
```

All 9 gates run **in parallel**. The final deploy gate requires all to succeed.

---

## Gate Specifications

### Gate 1: Build Reproducibility

**Purpose:** Prove that the same source produces the same binary.

**Method:**
1. Build the package from the same commit twice
2. Compute SHA-256 of both artifacts
3. Compare hashes

**Pass criteria:** Hashes are identical.

**Failure meaning:** Build process introduces nondeterminism (timestamps, random seeds, unstable ordering).

**Risk prevented:** "It works on my machine" — different builds from same source behave differently.

---

### Gate 2: Deterministic Execution

**Purpose:** Prove that identical inputs produce identical execution fingerprints.

**Method:**
1. Run the evaluation agent N times with the same input
2. Parse `evaluation_report.json`
3. Check reliability score, critical failure count, fingerprint mismatch count

**Pass criteria:**
- Reliability >= threshold (configurable)
- Zero critical failures
- Zero fingerprint mismatches

**Failure meaning:** Execution path varies across runs with identical input.

**Risk prevented:** Nondeterministic routing, agent selection, or output.

**Script:** `tests/ci/gate_deterministic_execution.py`

---

### Gate 3: WAL Replay Final-State

**Purpose:** Prove that replayed responses match original execution.

**Method:**
1. Execute an intent with full recording
2. Retrieve the response via `HistoricalResponseEngine`
3. Compare response hashes
4. Repeat 3 times for consistency

**Pass criteria:** All replay hashes match originals across all runs.

**Failure meaning:** Recording or retrieval corrupts execution state.

**Risk prevented:** Historical responses that don't match what actually happened.

**Script:** `tests/ci/gate_wal_replay_state.py`

---

### Gate 4: Entropy Detection

**Purpose:** Block unseeded randomness in deterministic-critical code paths.

**Method:**
1. Static scan of all Python files in `src/intentusnet/` and `examples/`
2. Pattern matching for entropy sources:
   - `random.random()` / `random.randint()` without seed
   - `uuid.uuid4()` in step IDs or fingerprint computation
   - `time.time()` / `datetime.now()` in hash computation
   - `os.urandom()` in hash computation
3. Known-safe uses are allowlisted

**Pass criteria:** Zero unallowlisted entropy violations.

**Failure meaning:** Nondeterministic randomness could affect execution paths.

**Risk prevented:** Subtle nondeterminism from randomness that only manifests intermittently.

**Script:** `tests/ci/gate_entropy_detection.py`

---

### Gate 5: Container Reproducibility

**Purpose:** Prove that the same Dockerfile produces the same image.

**Method:**
1. Build container image twice from same context
2. Compare image SHA-256 hashes

**Pass criteria:** Image hashes are identical.

**Failure meaning:** Dockerfile introduces nondeterminism (unpinned dependencies, timestamps).

**Risk prevented:** Container drift between builds.

---

### Gate 6: Routing Determinism

**Purpose:** Prove that agent selection is deterministic for the same input.

**Method:**
1. Register N agents with distinct priorities
2. Submit identical intents 10 times
3. Record which agent handles each intent and the response hash

**Pass criteria:** Same agent selected and same response hash across all 10 runs.

**Failure meaning:** Routing logic is nondeterministic.

**Risk prevented:** Different agents handling the same intent in different environments.

**Script:** `tests/ci/gate_routing_determinism.py`

---

### Gate 7: Crash Recovery

**Purpose:** Prove that crash recovery respects side-effect classification.

**Method:**
Four scenarios:
1. Reversible steps in progress → safe to resume
2. Irreversible step in progress → blocked (requires manual intervention)
3. Completed execution → excluded from recovery
4. Partial WAL write → hash chain survives

**Pass criteria:** All 4 scenarios produce expected recovery decisions.

**Failure meaning:** Recovery manager makes unsafe decisions.

**Risk prevented:** Re-executing irreversible operations after a crash.

**Script:** `tests/ci/gate_crash_recovery.py`

---

### Gate 8: WAL Integrity & Tamper Detection

**Purpose:** Prove that WAL hash chains detect tampering.

**Method:**
Four tests:
1. Write WAL entries → verify hash chain integrity
2. Tamper with an entry → verify detection
3. Write signed WAL entries → verify Ed25519 signatures
4. Tamper with signed entry → verify signature rejection

**Pass criteria:** Integrity verified for clean WAL; tampering detected for modified WAL.

**Failure meaning:** WAL cannot be trusted as source of truth.

**Risk prevented:** Undetected corruption or manipulation of execution history.

**Script:** `tests/ci/gate_wal_integrity.py`

---

### Gate 9: Runtime Snapshot

**Purpose:** Prove that execution records survive serialization round-trips.

**Method:**
1. Execute an intent
2. Serialize the `ExecutionRecord` to JSON
3. Deserialize back to `ExecutionRecord`
4. Compare content hashes and execution headers

**Pass criteria:** Round-tripped record is identical to original.

**Failure meaning:** Serialization loses or corrupts execution state.

**Risk prevented:** Records that cannot be reliably stored or transmitted.

**Script:** `tests/ci/gate_runtime_snapshot.py`

---

## Final Deploy Gate

The deploy gate (`deterministic-safe-deploy`) requires **all 9 gates + unit tests** to pass:

```yaml
needs:
  - unit-tests
  - gate-1-build-reproducibility
  - gate-2-deterministic-execution
  - gate-3-wal-replay-state
  - gate-4-entropy-detection
  - gate-5-container-reproducibility
  - gate-6-routing-determinism
  - gate-7-crash-recovery
  - gate-8-wal-integrity
  - gate-9-runtime-snapshot
```

If any gate fails, the deploy gate fails, and the release is blocked.

---

## Running Gates Locally

All gate scripts can be run locally:

```bash
# Individual gates
python tests/ci/gate_deterministic_execution.py
python tests/ci/gate_wal_replay_state.py
python tests/ci/gate_entropy_detection.py
python tests/ci/gate_routing_determinism.py
python tests/ci/gate_crash_recovery.py
python tests/ci/gate_wal_integrity.py
python tests/ci/gate_runtime_snapshot.py

# Full demo (includes all verification)
python -m examples.superdemo.demo
```

---

## References

- [Provable Determinism](determinism.md)
- [WAL Format](wal-format.md)
- [Runtime Determinism Core](runtime-determinism.md)
- Pipeline definition: `.github/workflows/deterministic-stability.yml`
