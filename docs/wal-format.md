# Write-Ahead Log (WAL) Format

## Overview

The WAL is the **source of truth** for all execution state in IntentusNet.

## File Format

- **Format:** JSONL (JSON Lines)
- **Encoding:** UTF-8
- **Extension:** `.wal`
- **Location:** `.intentusnet/wal/<execution-id>.wal`

## Entry Schema (v1.0)

```json
{
  "seq": 1,
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp_iso": "2026-01-03T10:30:00.123Z",
  "entry_type": "execution.started",
  "payload": {
    "execution_id": "550e8400-e29b-41d4-a716-446655440000",
    "envelope_hash": "sha256:abc123...",
    "intent_name": "search"
  },
  "prev_hash": null,
  "entry_hash": "sha256:def456...",
  "version": "1.0"
}
```

## Fields

### Core Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `seq` | integer | Yes | Monotonic sequence number (starts at 1) |
| `execution_id` | string (UUID) | Yes | Execution identifier |
| `timestamp_iso` | string (ISO 8601) | Yes | Entry timestamp |
| `entry_type` | string (enum) | Yes | Entry classification |
| `payload` | object | Yes | Entry-specific data |
| `prev_hash` | string \| null | Yes | SHA-256 of previous entry |
| `entry_hash` | string | Yes | SHA-256 of this entry |
| `version` | string | Yes | WAL schema version |

### Hash Computation

```python
data = {
    "seq": entry.seq,
    "execution_id": entry.execution_id,
    "timestamp_iso": entry.timestamp_iso,
    "entry_type": entry.entry_type,
    "payload": entry.payload,
    "prev_hash": entry.prev_hash,
    "version": entry.version,
}
encoded = json.dumps(data, sort_keys=True, separators=(",", ":"))
entry_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
```

## Entry Types

### Execution Lifecycle

#### `execution.started`

```json
{
  "entry_type": "execution.started",
  "payload": {
    "execution_id": "...",
    "envelope_hash": "sha256:...",
    "intent_name": "search"
  }
}
```

#### `execution.completed`

```json
{
  "entry_type": "execution.completed",
  "payload": {
    "execution_id": "...",
    "response_hash": "sha256:..."
  }
}
```

#### `execution.failed`

```json
{
  "entry_type": "execution.failed",
  "payload": {
    "execution_id": "...",
    "failure_type": "timeout",
    "reason": "Execution timeout",
    "recoverable": false
  }
}
```

#### `execution.aborted`

```json
{
  "entry_type": "execution.aborted",
  "payload": {
    "reason": "Manual abort",
    "aborted_by": "recovery_manager"
  }
}
```

### Step Lifecycle

#### `step.started`

**CRITICAL:** Written BEFORE step execution.

```json
{
  "entry_type": "step.started",
  "payload": {
    "step_id": "step-001",
    "agent_name": "search_agent",
    "side_effect": "read_only",
    "contracts": {
      "exactly_once": false,
      "timeout_ms": 5000
    },
    "input_hash": "sha256:..."
  }
}
```

#### `step.completed`

```json
{
  "entry_type": "step.completed",
  "payload": {
    "step_id": "step-001",
    "output_hash": "sha256:...",
    "success": true
  }
}
```

#### `step.failed`

```json
{
  "entry_type": "step.failed",
  "payload": {
    "step_id": "step-001",
    "failure_type": "agent_error",
    "reason": "Agent crashed",
    "recoverable": false
  }
}
```

### Fallback

#### `fallback.triggered`

```json
{
  "entry_type": "fallback.triggered",
  "payload": {
    "from_agent": "primary_agent",
    "to_agent": "fallback_agent",
    "reason": "Primary agent failed"
  }
}
```

#### `fallback.exhausted`

```json
{
  "entry_type": "fallback.exhausted",
  "payload": {
    "last_agent": "final_fallback_agent",
    "reason": "All fallback agents failed"
  }
}
```

### Contracts

#### `contract.validated`

```json
{
  "entry_type": "contract.validated",
  "payload": {
    "step_id": "step-001",
    "contracts": {
      "exactly_once": true,
      "timeout_ms": 5000
    }
  }
}
```

#### `contract.violated`

```json
{
  "entry_type": "contract.violated",
  "payload": {
    "step_id": "step-001",
    "contract": "timeout_ms",
    "reason": "Execution exceeded timeout (6000ms > 5000ms)"
  }
}
```

### Recovery

#### `recovery.started`

```json
{
  "entry_type": "recovery.started",
  "payload": {
    "completed_steps": ["step-001", "step-002"],
    "state": "in_progress"
  }
}
```

#### `recovery.completed`

```json
{
  "entry_type": "recovery.completed",
  "payload": {
    "resumed_from_step": "step-003",
    "state": "completed"
  }
}
```

### Checkpoint

#### `checkpoint`

```json
{
  "entry_type": "checkpoint",
  "payload": {
    "state": "in_progress",
    "completed_steps": ["step-001", "step-002"]
  }
}
```

## Integrity Verification

### Hash Chain

Each entry includes:
- `prev_hash`: SHA-256 of previous entry
- `entry_hash`: SHA-256 of this entry

First entry has `prev_hash = null`.

### Verification Algorithm

```python
prev_hash = None
for entry in wal_entries:
    # Check sequence
    assert entry.seq == expected_seq

    # Check hash chain
    assert entry.prev_hash == prev_hash

    # Verify entry hash
    computed_hash = entry.compute_hash()
    assert entry.entry_hash == computed_hash

    prev_hash = entry.entry_hash
    expected_seq += 1
```

## Guarantees

1. **Atomicity:** Each entry is written atomically (single write + fsync)
2. **Ordering:** Entries are strictly ordered by `seq`
3. **Integrity:** Hash chain detects corruption or truncation
4. **Durability:** `fsync()` before write returns
5. **Append-only:** No overwrites or deletions

## Crash Safety

WAL is **kill -9 safe**:

- All writes are fsynced before returning
- Incomplete writes are detected by missing entry or broken hash chain
- Recovery scans WAL and reconstructs state

## Example: Complete Execution

```jsonl
{"seq":1,"execution_id":"exec-001","entry_type":"execution.started","payload":{"envelope_hash":"abc123","intent_name":"search"},"prev_hash":null,"entry_hash":"hash1","version":"1.0"}
{"seq":2,"execution_id":"exec-001","entry_type":"step.started","payload":{"step_id":"step1","agent_name":"agent1","side_effect":"read_only","contracts":{},"input_hash":"hash_in1"},"prev_hash":"hash1","entry_hash":"hash2","version":"1.0"}
{"seq":3,"execution_id":"exec-001","entry_type":"step.completed","payload":{"step_id":"step1","output_hash":"hash_out1","success":true},"prev_hash":"hash2","entry_hash":"hash3","version":"1.0"}
{"seq":4,"execution_id":"exec-001","entry_type":"execution.completed","payload":{"response_hash":"resp_hash"},"prev_hash":"hash3","entry_hash":"hash4","version":"1.0"}
```

## Versioning

Current version: **1.0**

Future versions will:
- Add fields (backward compatible)
- Never remove required fields
- Include migration path
