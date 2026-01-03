```# IntentusNet v1 Production Hardening

## Overview

IntentusNet v1 is production-hardened with operator-grade execution guarantees, crash safety, and deterministic replay.

**Core Guarantees:**
- ✅ Double execution is impossible (idempotency + locking)
- ✅ Replay is deterministic or fails loudly
- ✅ WAL and Records are verifiably consistent
- ✅ Kill -9 safe (WAL with fsync)
- ✅ Explicit state machine (legal transitions only)
- ✅ Operator-complete CLI (CI-friendly exit codes)

---

## Production Features

### 1. Execution Lifecycle State Machine

**States:**
```
CREATED → STARTED → IN_PROGRESS → COMPLETED | FAILED | ABORTED
FAILED → RECOVERING → IN_PROGRESS | ABORTED
```

**Rules:**
- All state transitions are validated
- Illegal transitions fail immediately
- All transitions persisted in WAL
- Terminal states: COMPLETED, ABORTED

**CLI:**
```bash
intentusnet execution status <execution-id>
intentusnet execution wait <execution-id> [--timeout N]
intentusnet execution abort <execution-id> [--reason "..."]
```

---

### 2. Idempotency Keys

**Purpose:** Prevent duplicate execution across restarts.

**Behavior:**
- Optional `idempotency_key` in intent envelope
- Duplicate detected → return existing `execution_id`
- Idempotency resolution persisted in WAL
- Deterministic key computation from envelope

**Example:**
```json
{
  "idempotency_key": "user-123-search-2026-01-03",
  "intent": {...}
}
```

**Duplicate execution returns:**
```json
{
  "execution_id": "existing-exec-id",
  "duplicate": true
}
```

---

### 3. Execution Concurrency Locking

**Purpose:** Prevent concurrent execution of same execution_id.

**Implementation:**
- File-based advisory locks
- Stale lock detection (PID check + timeout)
- Lock ownership tracked in WAL

**Behavior:**
- Concurrent execution → `ValueError`
- Stale lock (process dead or timeout) → cleaned automatically
- Lock timeout: 1 hour (configurable)

---

### 4. Agent Invocation Determinism Boundary

**Purpose:** Ensure deterministic replay by tracking input/output hashes.

**What's tracked:**
- Input hash (before agent invocation)
- Output hash (after agent invocation)
- Agent version or digest
- Invocation metadata

**Replay verification:**
- Input hash must match
- Output hash must match
- Agent version must match

**Violation handling:**
- Policy: FAIL | WARN | RECORD_ONLY
- FAIL mode → immediate failure on mismatch
- WARN mode → log warning, continue
- RECORD_ONLY → record but don't enforce

---

### 5. Agent Version Pinning

**Purpose:** Prevent replay divergence due to agent changes.

**What's tracked:**
- Agent name
- Version string (e.g., "1.2.3")
- Content digest (SHA-256 of agent code)
- Metadata

**Replay behavior:**
- Version mismatch → fail replay
- Digest mismatch → fail replay

**CLI:**
```bash
intentusnet agents list
intentusnet agents describe <agent>
intentusnet agents versions <agent>
```

---

### 6. Determinism Enforcement Policy

**Policies:**
- `FAIL` (default) - Fail on determinism violation
- `WARN` - Log warning, continue execution
- `RECORD_ONLY` - Record violation but don't enforce

**What's enforced:**
- Input hash consistency
- Output hash consistency
- Agent version consistency

**CLI:**
```bash
intentusnet execution verify <execution-id>
```

**Exit codes:**
- `0` - Verified successfully
- `1` - Verification failed

---

### 7. Execution Records Lifecycle

**Record States:**
- `CREATED` - Record created, no data
- `PARTIAL` - Has events but not finalized
- `FINALIZED` - Complete and immutable
- `CORRUPTED` - Hash invalid or inconsistent

**Record finalization:**
- Computes and stores record hash
- Marks record immutable
- Links to WAL sequence numbers

**CLI:**
```bash
intentusnet records list
intentusnet records show <execution-id>
intentusnet records verify <execution-id>
intentusnet records stats
```

---

### 8. WAL ↔ Record Consistency Enforcement

**Checks:**
- Every completed WAL step has corresponding record entry
- Envelope hashes match (WAL vs Record)
- No orphaned records or WAL entries
- Hash integrity verified

**Violations:**
- `envelope_hash_mismatch` - WAL and Record envelope hashes differ
- `steps_missing_in_record` - WAL has steps not in record
- `extra_steps_in_record` - Record has steps not in WAL
- `wal_corrupted` - WAL integrity check failed
- `record_corrupted` - Record hash invalid

**CLI:**
```bash
intentusnet execution verify <execution-id>
intentusnet records verify <execution-id>
```

**Exit codes:**
- `0` - Consistent
- `1` - Inconsistent (violations found)

---

### 9. Security Guardrails

**Authentication:**
- Environment-based auth token
- `INTENTUSNET_AUTH_TOKEN` environment variable
- No token → allow (for local development)

**Read-Only Mode:**
- `INTENTUSNET_MODE=read_only`
- Mutating operations → `PermissionError`

**Destructive Operation Confirmation:**
- Requires explicit confirmation
- Auto-confirm: `INTENTUSNET_AUTO_CONFIRM=1` (for CI)
- Interactive mode: type "yes" to confirm

**Example:**
```bash
export INTENTUSNET_AUTH_TOKEN="secret-token"
export INTENTUSNET_MODE=read_only

intentusnet execution abort exec-001 --reason "test"
# Error: Operation 'abort' not allowed in read-only mode
```

---

## CLI Reference

### Execution Commands

```bash
# Show execution status
intentusnet execution status <execution-id>

# Wait for execution to complete
intentusnet execution wait <execution-id> [--timeout N]

# Abort execution (requires confirmation)
intentusnet execution abort <execution-id> [--reason "..."]

# Verify execution integrity
intentusnet execution verify <execution-id> [--replay]
```

### WAL Commands

```bash
# Inspect WAL entries
intentusnet wal inspect <execution-id>

# Verify WAL integrity
intentusnet wal verify <execution-id>

# Tail WAL (last N entries)
intentusnet wal tail <execution-id> [--lines N]

# WAL statistics
intentusnet wal stats
```

### Record Commands

```bash
# List all records
intentusnet records list

# Show record details
intentusnet records show <execution-id>

# Verify record integrity
intentusnet records verify <execution-id>

# Diff two records
intentusnet records diff <id1> <id2>

# Record statistics
intentusnet records stats

# Garbage collect old records (requires confirmation)
intentusnet records gc --older-than 30
```

### Recovery Commands

```bash
# Scan for incomplete executions
intentusnet recovery scan

# Resume execution
intentusnet recovery resume <execution-id>

# Abort execution (requires confirmation)
intentusnet recovery abort <execution-id> --reason "..."
```

### Replay Command

```bash
# Replay execution
intentusnet replay <execution-id>

# Dry run (no side effects)
intentusnet replay <execution-id> --dry-run
```

### Contract Commands

```bash
# Validate contract
intentusnet contracts validate <intent.json>

# Show contracts for execution
intentusnet contracts show <execution-id>

# Show contract violations
intentusnet contracts violations <execution-id>
```

### Agent Commands

```bash
# List agents
intentusnet agents list

# Describe agent
intentusnet agents describe <agent>

# Show agent versions
intentusnet agents versions <agent>

# Check agent health
intentusnet agents health
```

### Cost Commands

```bash
# Estimate cost
intentusnet cost estimate <intent.json> [--budget N]

# Show execution cost
intentusnet cost show <execution-id>

# Top N by cost
intentusnet cost top [--n N]

# Budget status
intentusnet cost budget-status
```

---

## CLI Output Formats

All commands support:

```bash
--output json|jsonl|table
```

**JSON output (default for programmatic use):**
```bash
intentusnet records list --output json
```

**Table output (default for human use):**
```bash
intentusnet records list --output table
```

**JSONL output (for streaming):**
```bash
intentusnet wal inspect <id> --output jsonl
```

---

## Exit Codes

**Deterministic exit codes:**

- `0` - Success
- `1` - General error
- `2` - Verification failed
- `130` - Interrupted (Ctrl+C)

**Verification commands:**
- `intentusnet execution verify` - 0 if verified, 1 if violations
- `intentusnet wal verify` - 0 if verified, 1 if corrupted
- `intentusnet records verify` - 0 if verified, 1 if issues

---

## Production Deployment

### Required Environment Variables

```bash
# Auth token (production)
export INTENTUSNET_AUTH_TOKEN="your-secret-token"

# Read-only mode (optional)
export INTENTUSNET_MODE=read_write

# Auto-confirm for CI (optional)
export INTENTUSNET_AUTO_CONFIRM=1
```

### Directory Structure

```
.intentusnet/
├── wal/              # Write-Ahead Log
│   └── <execution-id>.wal
├── records/          # Execution records
│   └── <execution-id>.json
├── locks/            # Execution locks
│   └── <execution-id>.lock
└── idempotency/      # Idempotency keys
    └── idempotency_index.json
```

### Monitoring

**Health checks:**
```bash
# WAL directory accessible
intentusnet wal stats

# Record directory accessible
intentusnet records stats
```

**Integrity checks:**
```bash
# Verify all executions
for id in $(intentusnet records list --output json | jq -r '.records[]'); do
  intentusnet execution verify $id || echo "FAILED: $id"
done
```

---

## Operator Recovery Guide

### Scenario 1: Process Crash (kill -9)

```bash
# Scan for incomplete executions
intentusnet recovery scan

# For each incomplete execution:
intentusnet recovery resume <execution-id>

# Or abort if unrecoverable:
intentusnet recovery abort <execution-id> --reason "Process crashed"
```

### Scenario 2: Inconsistent WAL/Record

```bash
# Verify execution
intentusnet execution verify <execution-id>

# If inconsistent, check violations:
intentusnet records verify <execution-id>

# Manual intervention required
```

### Scenario 3: Stale Lock

```bash
# Stale locks are cleaned automatically
# Manual cleanup:
rm .intentusnet/locks/<execution-id>.lock
```

### Scenario 4: Replay Divergence

```bash
# Verify replay determinism
intentusnet execution verify <execution-id> --replay

# Check determinism policy
# If FAIL mode, execution will fail on divergence
```

---

## Testing

**Run production tests:**
```bash
pytest tests/test_state_machine.py -v
pytest tests/test_idempotency.py -v
pytest tests/test_locking.py -v
pytest tests/test_consistency.py -v
```

**Kill -9 simulation:**
```bash
# Start execution in background
intentusnet execution start intent.json &
PID=$!

# Kill process
kill -9 $PID

# Verify recovery
intentusnet recovery scan
```

---

## Failure Semantics

**Double Execution Prevention:**
- Idempotency keys deduplicate requests
- Execution locks prevent concurrent execution
- State machine enforces legal transitions

**Crash Safety:**
- WAL written BEFORE side effects
- fsync guarantees durability
- Recovery reconstructs state from WAL

**Deterministic Replay:**
- Input/output hashes tracked
- Agent versions pinned
- Replay follows recorded plan only

**Fail Fast, Fail Loud:**
- Illegal state transition → `IllegalStateTransitionError`
- Contract violation → fail before execution
- Determinism violation → fail replay (FAIL mode)
- WAL corruption → fail immediately

---

## Non-Goals

❌ Web UI - Use CLI + jq
❌ Implicit retries - Must be declared in contracts
❌ Best-effort execution - Determinism > convenience
❌ Eventual consistency - Fail immediately on inconsistency

---

## Version History

**v1.0 - Production Hardening**
- Execution lifecycle state machine
- Idempotency keys
- Execution locking
- Agent versioning
- Determinism enforcement
- WAL ↔ Record consistency
- Security guardrails
- Complete CLI suite
```
