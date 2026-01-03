# Execution Contracts

## Overview

Execution contracts are **runtime-enforced guarantees** that IntentusNet validates and upholds during execution.

Contracts make implicit assumptions **explicit and enforceable**.

## Contract Types

### 1. `exactly_once`

**Guarantee:** Step executes exactly once.

```python
ExecutionContract(exactly_once=True)
```

**Runtime behavior:**
- Runtime tracks completed steps
- Duplicate execution → `CONTRACT_VIOLATION`
- WAL records step completion

**Use cases:**
- Database writes
- Payment processing
- Irreversible actions

**Validation:**
- Compatible with all side-effect classes
- Requires WAL

---

### 2. `no_retry`

**Guarantee:** Step will not be retried on failure.

```python
ExecutionContract(no_retry=True)
```

**Runtime behavior:**
- Failure → immediate abort
- No retry logic applied
- Fallback may still trigger (different agent)

**Use cases:**
- Non-idempotent operations
- Time-sensitive operations
- Explicit failure handling required

**Validation:**
- Cannot combine with `max_retries`

---

### 3. `max_retries`

**Guarantee:** Step will retry up to N times.

```python
ExecutionContract(max_retries=3)
```

**Runtime behavior:**
- Failure → retry (up to N times)
- Exponential backoff (configurable)
- After N retries → final failure

**Use cases:**
- Transient failures
- Network operations
- Idempotent operations

**Validation:**
- ❌ NOT compatible with `side_effect=irreversible`
- ❌ Cannot combine with `no_retry`

---

### 4. `idempotent_required`

**Guarantee:** Agent declares idempotency.

```python
ExecutionContract(idempotent_required=True)
```

**Runtime behavior:**
- Declarative contract (agent responsibility)
- Runtime does not enforce (cannot verify)
- Enables retry logic

**Use cases:**
- Documenting agent properties
- Enabling safe retries
- Compliance requirements

**Validation:**
- Always valid (declarative)

---

### 5. `timeout_ms`

**Guarantee:** Step completes within timeout.

```python
ExecutionContract(timeout_ms=5000)
```

**Runtime behavior:**
- Execution tracked with timer
- Timeout exceeded → `TIMEOUT` failure
- WAL records timeout violation

**Use cases:**
- Preventing hung executions
- SLA enforcement
- Resource management

**Validation:**
- Must be positive integer

---

### 6. `max_cost_units`

**Guarantee:** Step cost does not exceed limit.

```python
ExecutionContract(max_cost_units=100)
```

**Runtime behavior:**
- Pre-execution cost estimation
- Estimated cost > limit → fail before execution
- Actual cost tracked (for analysis)

**Use cases:**
- Budget enforcement
- Cost control
- Preventing runaway costs

**Validation:**
- Must be positive number

---

## Side-Effect Classes

Every step MUST declare its side-effect class.

### `READ_ONLY`

**Semantics:** No state changes.

**Guarantees:**
- ✅ Safe to replay
- ✅ Retry allowed
- ✅ Fallback allowed

**Examples:**
- Database reads
- API GET requests
- File reads

---

### `REVERSIBLE`

**Semantics:** Changes can be undone.

**Guarantees:**
- ✅ Retry allowed (with compensation)
- ✅ Fallback allowed
- ⚠️  WAL recommended

**Examples:**
- Database writes (with rollback)
- Temporary file creation
- Reversible API calls

**Compensation Required:**
- Agent must implement rollback logic

---

### `IRREVERSIBLE`

**Semantics:** Cannot be undone.

**Guarantees:**
- ❌ NO retry
- ❌ NO fallback
- ✅ WAL REQUIRED (written BEFORE execution)

**Examples:**
- Payment processing
- Email sending
- Audit log writes
- External system notifications

**WAL Requirement:**
```python
# BEFORE execution
wal.step_started(
    step_id="payment-001",
    agent_name="payment_agent",
    side_effect="irreversible",  # <-- REQUIRED
    contracts={"exactly_once": True},
    input_hash="sha256:..."
)

# Execute
result = execute_payment()

# AFTER execution
wal.step_completed("payment-001", output_hash, success=True)
```

---

## Contract Validation Rules

### Valid Combinations

| Contract | read_only | reversible | irreversible |
|----------|-----------|------------|--------------|
| `exactly_once` | ✅ | ✅ | ✅ |
| `no_retry` | ✅ | ✅ | ✅ |
| `max_retries` | ✅ | ✅ | ❌ |
| `idempotent_required` | ✅ | ✅ | ✅ |
| `timeout_ms` | ✅ | ✅ | ✅ |
| `max_cost_units` | ✅ | ✅ | ✅ |

### Invalid Combinations

- ❌ `max_retries` + `side_effect=irreversible`
  - **Reason:** Irreversible steps cannot be retried
  - **Error:** `CONTRACT_VIOLATION`

- ❌ `no_retry=True` + `max_retries > 0`
  - **Reason:** Contradictory contracts
  - **Error:** `CONTRACT_VIOLATION`

- ❌ `timeout_ms <= 0`
  - **Reason:** Invalid timeout
  - **Error:** `CONTRACT_VIOLATION`

- ❌ `max_cost_units <= 0`
  - **Reason:** Invalid budget
  - **Error:** `CONTRACT_VIOLATION`

---

## Fallback Chain Rules

### Side-Effect Transitions

When fallback occurs, side-effect class may change:

| From | To | Allowed? | Notes |
|------|----|----------|-------|
| `read_only` | `read_only` | ✅ | Safe |
| `read_only` | `reversible` | ✅ | Escalation allowed |
| `read_only` | `irreversible` | ✅ | Escalation allowed |
| `reversible` | `reversible` | ✅ | Safe |
| `reversible` | `irreversible` | ⚠️ | Allowed but logged |
| `irreversible` | ANY | ❌ | **FORBIDDEN** |

### Irreversible Barrier

Once an irreversible step executes, **no fallback is allowed**.

**Reason:** Cannot undo irreversible effects.

**Example:**

```python
# Primary agent (irreversible)
wal.step_started("step1", "payment_agent", "irreversible", ...)
execute_payment()  # <-- Payment processed
wal.step_completed("step1", ...)

# If this fails, CANNOT fallback
# Payment already sent!
```

**Solution:** Use reversible operations for fallback chains:

```python
# Primary agent (reversible)
wal.step_started("step1", "auth_payment", "reversible", ...)
authorize_payment()  # <-- Authorization (can be reversed)

# If authorized payment fails, can fallback
# Authorization can be cancelled
```

---

## Contract Enforcement

### Pre-Execution Validation

```python
from intentusnet.contracts import ContractValidator, SideEffectClass

contract = ExecutionContract(
    max_retries=3,
    timeout_ms=5000
)

violation = ContractValidator.validate_contract(
    contract,
    SideEffectClass.IRREVERSIBLE  # ❌ max_retries + irreversible
)

if violation:
    # Execution fails BEFORE starting
    raise ContractViolationError(violation)
```

### Runtime Enforcement

```python
from intentusnet.contracts import ContractEnforcer

# Check if retry allowed
can_retry, reason = ContractEnforcer.can_retry(
    contract,
    side_effect=SideEffectClass.REVERSIBLE,
    attempt_number=2
)

if not can_retry:
    # Retry not allowed
    fail_execution(reason)
```

### Timeout Enforcement

```python
# Enforce timeout
try:
    result = ContractEnforcer.enforce_timeout(
        fn=lambda: execute_step(),
        timeout_ms=5000,
        step_id="step-001"
    )
except ContractEnforcementError as e:
    # Timeout violated
    wal.contract_violated("step-001", "timeout_ms", str(e))
```

---

## Example: Payment Processing

```python
from intentusnet.contracts import ExecutionContract, SideEffectClass
from intentusnet.wal import WALWriter

# Define contract
contract = ExecutionContract(
    exactly_once=True,      # Payment must execute exactly once
    no_retry=True,          # Cannot retry payment
    timeout_ms=10000,       # Must complete in 10s
    max_cost_units=50,      # Budget limit
)

# Validate contract
violation = ContractValidator.validate_contract(
    contract,
    SideEffectClass.IRREVERSIBLE
)
assert violation is None  # ✅ Valid

# Execute with WAL
with WALWriter(wal_dir, execution_id) as wal:
    # Write BEFORE execution
    wal.step_started(
        step_id="payment-001",
        agent_name="stripe_payment",
        side_effect="irreversible",
        contracts=contract.to_dict(),
        input_hash=sha256(payment_params)
    )

    # Execute payment
    try:
        result = process_payment(payment_params)

        # Write completion
        wal.step_completed(
            "payment-001",
            output_hash=sha256(result),
            success=True
        )
    except Exception as e:
        # Write failure
        wal.step_failed(
            "payment-001",
            failure_type="payment_error",
            reason=str(e),
            recoverable=False  # Irreversible step failed
        )
        raise
```

---

## Contract Violations

All violations produce structured failures:

```python
{
  "failure_type": "contract_violation",
  "execution_id": "exec-001",
  "step_id": "payment-001",
  "reason": "Timeout exceeded (12000ms > 10000ms)",
  "details": {
    "contract": "timeout_ms",
    "limit": 10000,
    "actual": 12000
  },
  "recoverable": false,
  "recovery_strategy": "abort"
}
```

---

## Best Practices

1. **Declare side-effects accurately**
   - Misclassification breaks safety guarantees

2. **Use `exactly_once` for irreversible steps**
   - Prevents duplicate execution

3. **Prefer `reversible` over `irreversible`**
   - Enables fallback and retry

4. **Set timeouts for all network operations**
   - Prevents hung executions

5. **Validate contracts before deployment**
   - Catch invalid combinations early

6. **WAL BEFORE irreversible operations**
   - Ensures crash safety

---

## References

- **WAL Format:** `docs/wal-format.md`
- **Runtime Determinism:** `docs/runtime-determinism.md`
- **RFC-0001:** Debuggable LLM Execution
