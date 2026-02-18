# Replay, WAL, and Crash Recovery

## Overview

IntentusNet provides three interconnected systems that ensure execution state is never lost:

1. **Write-Ahead Log (WAL)** — append-only, hash-chained execution journal
2. **Execution Recording & Replay** — immutable execution artifacts with historical retrieval
3. **Crash Recovery** — deterministic recovery decisions based on side-effect classification

---

## Write-Ahead Log (WAL)

The WAL is the **source of truth** for all execution state.

### Properties

| Property | Description |
|----------|-------------|
| Append-only | Entries are never overwritten or deleted |
| Hash-chained | Each entry includes SHA-256 of the previous entry |
| fsync-before-return | All writes are fsynced to disk before returning |
| Pre-execution writes | `step.started` is written BEFORE agent execution |
| JSONL format | One JSON object per line, UTF-8 encoded |

### Entry Types

**Execution lifecycle:** `execution.started`, `execution.completed`, `execution.failed`, `execution.aborted`

**Step lifecycle:** `step.started`, `step.completed`, `step.failed`, `step.skipped`

**Fallback:** `fallback.triggered`, `fallback.exhausted`

**Contracts:** `contract.validated`, `contract.violated`

**Recovery:** `recovery.started`, `recovery.completed`

### Hash Chain Integrity

```
Entry 1: prev_hash=null,    entry_hash=H1
Entry 2: prev_hash=H1,      entry_hash=H2
Entry 3: prev_hash=H2,      entry_hash=H3
```

If any entry is tampered with, the hash chain breaks — detected immediately on read.

### Signed WAL (REGULATED Mode)

In REGULATED compliance mode, each WAL entry includes an **Ed25519 signature**:

```json
{
  "seq": 1,
  "entry_type": "execution.started",
  "payload": {...},
  "entry_hash": "sha256:...",
  "signature": "ed25519:..."
}
```

Signatures are verified on read. A tampered entry fails signature verification even if the hash chain is rebuilt.

### CLI Commands

```bash
# Inspect WAL entries
intentusnet wal inspect <execution-id>

# Verify WAL integrity
intentusnet wal verify <execution-id>
```

For the complete WAL format specification, see [wal-format.md](wal-format.md).

---

## Execution Recording & Replay

### Recording

Every execution is recorded as a first-class **immutable artifact**, not a transient log:

- Full execution trace (routing decisions, agent calls, responses)
- Stable content hash for integrity verification
- Stored independently of the WAL (WAL provides crash safety; records provide retrieval)

### Historical Response Retrieval

The `HistoricalResponseEngine` returns stored responses **without re-executing any code**:

```python
from intentusnet.recording.replay import HistoricalResponseEngine
from intentusnet.recording.store import FileExecutionStore

store = FileExecutionStore(record_dir)
engine = HistoricalResponseEngine(store)

# Returns stored response — no agent code runs
response = engine.retrieve(execution_id)
```

**Guarantees:**
- No agent code is executed
- No model is called
- No routing logic runs
- Response is byte-for-byte identical to the original

### WAL Replay Verification

IntentusNet v1.5.1 adds **replay verification** — proving that the stored response matches the original execution:

1. Execute an intent (produces execution record + response hash)
2. Retrieve via `HistoricalResponseEngine` (produces replay hash)
3. Compare hashes → must be identical

This is enforced in CI as **Gate 3: WAL Replay Final-State**.

### Model Swap Safety

When a model is upgraded:

- **New executions** use the new model
- **Historical records** remain intact — retrieving a past execution returns the original response
- The old model's behavior is preserved as an immutable fact

```
v1 model execution → recorded → v2 model deployed
                                  │
retrieve(v1_execution_id) → returns v1 response (unchanged)
```

---

## Crash Recovery

### Overview

The `RecoveryManager` handles incomplete executions after crashes (including `kill -9`).

### Recovery Algorithm

1. Scan WAL directory for incomplete executions
2. For each incomplete execution:
   - Read WAL with integrity verification
   - Reconstruct execution state
   - Classify pending steps by side-effect class
   - Decide: RESUME or BLOCK

### Recovery Rules

| Condition | Decision | Reason |
|-----------|----------|--------|
| All pending steps are `read_only` | RESUME | Safe to re-execute |
| All pending steps are `reversible` | RESUME | Can be compensated |
| Any `irreversible` step started but not completed | BLOCK | Cannot determine if side effect occurred |
| WAL integrity check failed | BLOCK | State is untrustworthy |
| Ambiguous state | BLOCK | Conservative default |

### Side-Effect Classification

Every step declares its side-effect class:

| Class | Retry Safe | Fallback Safe | WAL Required |
|-------|-----------|--------------|-------------|
| `READ_ONLY` | Yes | Yes | No |
| `REVERSIBLE` | Yes (with compensation) | Yes | Recommended |
| `IRREVERSIBLE` | **No** | **No** | **Required** |

### CLI Commands

```bash
# Scan for incomplete executions
intentusnet recovery scan

# Resume an execution (only if safe)
intentusnet recovery resume <execution-id>

# Abort an execution
intentusnet recovery abort <execution-id> --reason "Manual abort"
```

### CI Gate: Crash Recovery

Crash recovery correctness is enforced in CI as **Gate 7**, which tests 4 scenarios:

1. Reversible steps in progress → safe to resume
2. Irreversible step in progress → blocked
3. Completed execution → excluded from recovery
4. Partial WAL write → hash chain survives

---

## How the Three Systems Interact

```
Intent Execution
       │
       ├── WAL: step.started (written BEFORE execution)
       │
       ├── Agent executes
       │
       ├── WAL: step.completed (written AFTER execution)
       │
       ├── Execution Record: stored as immutable artifact
       │
       └── Done
           │
           ├── Retrieve: HistoricalResponseEngine returns stored response
           │
           └── Crash? → RecoveryManager reads WAL → decides RESUME or BLOCK
```

- **WAL** ensures crash safety (no state lost on kill -9)
- **Execution Records** ensure retrievability (no model re-execution needed)
- **Recovery Manager** ensures safe restart (no irreversible operations re-executed)

---

## References

- [WAL Format Specification](wal-format.md)
- [Runtime Determinism Core](runtime-determinism.md)
- [Provable Determinism](determinism.md)
- [CI/CD Gate Specification](ci-cd.md)
