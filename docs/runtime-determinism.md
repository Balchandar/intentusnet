# Runtime Determinism Core

## Overview

The Runtime Determinism Core makes IntentusNet a **crash-safe, replayable, contract-enforced, operator-trustworthy execution runtime** for debuggable LLM + tool workflows.

After any execution, the runtime can answer:
- **What happened?** (complete execution trace)
- **Why was this path chosen?** (deterministic routing decisions)
- **What fallback occurred?** (recorded fallback chain)
- **Is it safe to retry?** (side-effect classification)
- **Can this execution be replayed?** (deterministic replay)

## Core Components

### 1. Write-Ahead Log (WAL)

**Location:** `src/intentusnet/wal/`

The WAL is:
- **Append-only** (JSONL format)
- **Written BEFORE side effects** (crash safety)
- **Hash-chained** (integrity verification)
- **The source of truth** for execution state

#### WAL Format

Each WAL entry includes:
```json
{
  "seq": 1,
  "execution_id": "abc123",
  "timestamp_iso": "2026-01-03T10:30:00Z",
  "entry_type": "execution.started",
  "payload": {...},
  "prev_hash": null,
  "entry_hash": "sha256...",
  "version": "1.0"
}
```

#### Entry Types

- **Execution lifecycle:**
  - `execution.started`
  - `execution.completed`
  - `execution.failed`
  - `execution.aborted`

- **Step lifecycle:**
  - `step.started` (MUST be written BEFORE execution)
  - `step.completed`
  - `step.failed`
  - `step.skipped`

- **Fallback:**
  - `fallback.triggered`
  - `fallback.exhausted`

- **Contracts:**
  - `contract.validated`
  - `contract.violated`

- **Recovery:**
  - `recovery.started`
  - `recovery.completed`

#### Guarantees

1. **Hash chain integrity:** Each entry includes hash of previous entry
2. **Monotonic sequence:** Sequence numbers are strictly increasing
3. **fsync before return:** All writes are fsynced
4. **Append-only:** No overwrites allowed

### 2. Crash Recovery

**Location:** `src/intentusnet/wal/recovery.py`

Crash recovery is:
- **Deterministic:** Same input → same recovery decision
- **Conservative:** If ambiguous → fail explicitly
- **Safe:** Never re-execute irreversible steps

#### Recovery Algorithm

1. **Scan WAL directory** for incomplete executions
2. **For each incomplete execution:**
   - Read WAL with integrity verification
   - Reconstruct execution state
   - Check for pending irreversible steps
   - Decide: RESUME or ABORT

#### Recovery Rules

- **RESUME if:**
  - All pending steps are `read_only` or `reversible`
  - No ambiguous irreversible step state

- **ABORT if:**
  - Irreversible step started but not completed
  - WAL integrity check failed
  - State is ambiguous

#### CLI Commands

```bash
# Scan for incomplete executions
intentusnet recovery scan

# Resume an execution
intentusnet recovery resume <execution-id>

# Abort an execution
intentusnet recovery abort <execution-id> --reason "Manual abort"
```

### 3. Execution Contracts

**Location:** `src/intentusnet/contracts/`

Contracts are **runtime-enforced guarantees**:

#### Available Contracts

```python
ExecutionContract(
    exactly_once=True,        # Step executes exactly once
    no_retry=True,            # No retries allowed
    max_retries=3,            # Maximum retry attempts
    idempotent_required=True, # Agent must be idempotent
    timeout_ms=5000,          # Maximum execution time
    max_cost_units=100,       # Budget limit
)
```

#### Contract Validation

Contracts are validated **BEFORE execution**:

```python
from intentusnet.contracts import ContractValidator, SideEffectClass

violation = ContractValidator.validate_contract(
    contract, SideEffectClass.IRREVERSIBLE
)

if violation:
    # Execution fails - runtime cannot guarantee contract
    raise ContractViolationError(violation)
```

#### Invalid Contract Combinations

- ❌ `max_retries > 0` + `side_effect=irreversible`
- ❌ `no_retry=True` + `max_retries > 0`
- ❌ `timeout_ms <= 0`

### 4. Side-Effect Classification

**Location:** `src/intentusnet/contracts/models.py`

Every step MUST declare its side-effect class:

#### Side-Effect Classes

```python
class SideEffectClass(Enum):
    READ_ONLY = "read_only"        # No state changes (safe to replay)
    REVERSIBLE = "reversible"      # Changes can be undone (retry allowed)
    IRREVERSIBLE = "irreversible"  # Cannot be undone (NO retry)
```

#### Rules

- **`read_only`:**
  - Safe to replay
  - Retry allowed
  - Fallback allowed

- **`reversible`:**
  - Retry allowed (with compensation)
  - Fallback allowed
  - WAL recommended

- **`irreversible`:**
  - **NO retry**
  - **NO fallback** (cannot fallback after irreversible)
  - **WAL REQUIRED** (written before execution)

#### Fallback Transitions

- ✅ `read_only` → `read_only`
- ✅ `read_only` → `reversible`
- ✅ `reversible` → `reversible`
- ⚠️  `reversible` → `irreversible` (escalation - allowed but logged)
- ❌ `irreversible` → ANY (FORBIDDEN)

### 5. Structured Failures

**Location:** `src/intentusnet/failures/`

All failures are **typed, structured, and queryable**.

#### Failure Types

```python
class FailureType(Enum):
    CONTRACT_VIOLATION = "contract_violation"
    TIMEOUT = "timeout"
    BUDGET_EXCEEDED = "budget_exceeded"
    NO_AGENT_FOUND = "no_agent_found"
    ROUTING_ERROR = "routing_error"
    AGENT_ERROR = "agent_error"
    WAL_INTEGRITY_ERROR = "wal_integrity_error"
    IRREVERSIBLE_STEP_FAILED = "irreversible_step_failed"
    # ...
```

#### Structured Failure Model

```python
StructuredFailure(
    failure_type=FailureType.TIMEOUT,
    execution_id="exec-001",
    step_id="step-1",
    agent_name="agent-1",
    reason="Execution timeout",
    details={"timeout_ms": 1000, "elapsed_ms": 1500},
    recoverable=True,
    recovery_strategy=RecoveryStrategy.RETRY,
    caused_by=None,  # Optional causality chain
)
```

#### Recovery Strategies

- `RETRY` - Can retry immediately
- `RETRY_AFTER_DELAY` - Can retry after delay
- `FALLBACK` - Try next agent in fallback chain
- `ABORT` - Cannot recover
- `MANUAL_INTERVENTION` - Requires operator action

### 6. Pre-Execution Cost Estimation

**Location:** `src/intentusnet/estimation/`

Estimates cost **BEFORE execution**:

#### Cost Model

```python
CostEstimate(
    execution_id="exec-001",
    intent_name="search",
    estimated_usage={
        ResourceType.AGENT_CALLS: 3.0,
        ResourceType.LLM_INPUT_TOKENS: 500.0,
        ResourceType.LLM_OUTPUT_TOKENS: 1000.0,
    },
    estimated_cost=150.0,
    budget_limit=100.0,
    exceeds_budget=True,  # FAIL FAST
)
```

#### Fail Fast on Budget

If `estimated_cost > budget_limit`, execution **fails before starting**.

#### CLI

```bash
intentusnet estimate intent.json --budget 100
```

### 7. Deterministic Replay

**Location:** `src/intentusnet/recording/replay.py`

Replay follows **recorded plan only** (no re-planning):

#### Replay Rules

- ✅ Replay uses **recorded output** (no re-execution)
- ✅ Irreversible steps **never re-execute**
- ✅ Divergence → **hard failure**
- ✅ `--dry-run` produces **zero side effects**

#### CLI

```bash
# Replay execution
intentusnet replay <execution-id>

# Dry run (no side effects)
intentusnet replay <execution-id> --dry-run

# Diff executions
intentusnet executions diff <id1> <id2>
```

### 8. CLI Inspection

**Location:** `src/intentusnet/cli/`

All CLI commands output **JSON/JSONL** (grep/jq friendly):

```bash
# List all executions
intentusnet executions list

# Show execution details
intentusnet executions show <execution-id>

# Show execution trace (WAL)
intentusnet executions trace <execution-id>

# Diff two executions
intentusnet executions diff <id1> <id2>

# Replay execution
intentusnet replay <execution-id> [--dry-run]

# Estimate cost
intentusnet estimate intent.json [--budget 100]

# Recovery
intentusnet recovery scan
intentusnet recovery resume <execution-id>
intentusnet recovery abort <execution-id> --reason "..."
```

### 9. Observability

**Location:** `src/intentusnet/observability/`

Standard observability endpoints:

#### `/health`

```json
{
  "status": "healthy",
  "checks": {
    "wal_directory": {"accessible": true, "path": "..."},
    "record_directory": {"accessible": true, "path": "..."}
  },
  "timestamp": "2026-01-03T10:30:00Z"
}
```

#### `/metrics` (Prometheus format)

```
# TYPE intentusnet_executions_total counter
intentusnet_executions_total 1234

# TYPE intentusnet_execution_duration_ms histogram
intentusnet_execution_duration_ms_count 1234
intentusnet_execution_duration_ms_sum 567890.0
```

## Architecture Decisions

### Why WAL?

**Problem:** Execution state can be lost on crash (kill -9).

**Solution:** WAL ensures all critical events are persisted before side effects.

### Why Hash Chaining?

**Problem:** WAL can be corrupted or truncated.

**Solution:** Hash chaining detects corruption and ensures integrity.

### Why Side-Effect Classification?

**Problem:** Not all operations are safe to retry.

**Solution:** Explicit classification enables runtime to enforce safety.

### Why Contracts?

**Problem:** Implicit retry/fallback logic causes hidden failures.

**Solution:** Explicit contracts make guarantees visible and enforceable.

### Why Structured Failures?

**Problem:** Generic exceptions are not queryable or debuggable.

**Solution:** Typed failures enable post-mortem analysis and automation.

## Non-Goals

- ❌ Web UI (use CLI + jq)
- ❌ Prompt engineering
- ❌ Agent intelligence
- ❌ Autonomous planning
- ❌ Implicit retries
- ❌ Cloud-specific adapters

## Migration Guide

### From Basic Runtime to Deterministic Runtime

```python
from intentusnet.core.runtime import IntentusRuntime
from intentusnet.core.deterministic_router import DeterministicRouter

# Basic runtime
runtime = IntentusRuntime()

# Wrap with deterministic router
deterministic_router = DeterministicRouter(
    runtime.router,
    wal_dir=".intentusnet/wal",
    enable_cost_estimation=True,
)

# Route with contracts
response = deterministic_router.route_intent(
    envelope,
    budget_limit=100.0,
    default_contract=ExecutionContract(exactly_once=True, timeout_ms=5000),
    default_side_effect=SideEffectClass.READ_ONLY,
)
```

## References

- **RFC-0001:** Debuggable LLM Execution
- **WAL Format:** `docs/wal-format.md`
- **Contract Spec:** `docs/contracts.md`
- **Failure Taxonomy:** `docs/failures.md`
