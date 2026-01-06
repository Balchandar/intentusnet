# Canonical IntentusNet Demo

This demo demonstrates the core capabilities of IntentusNet:

1. **Multi-target Intent Resolution** - A single intent resolves to multiple targets
2. **Target Filtering** - Dangerous targets are filtered before execution
3. **Deterministic Execution** - Agents execute in a predictable, reproducible order
4. **WAL-based Crash Safety** - Write-ahead log ensures crash recovery
5. **Execution Recording & Replay** - Executions can be replayed deterministically

## Scenario

**User Intent:** "Power off system for maintenance"

**Targets:**
- `server` - Main application server (allowed)
- `lights` - Facility lighting system (allowed)
- `cctv` - Security cameras (DANGEROUS - filtered out)

**Expected Behavior:**
1. The `maintenance-coordinator` agent receives the intent
2. It filters out `cctv` as a dangerous target
3. It executes power-off on `server` and `lights` only
4. The `cctv` power-off is NEVER executed

## Running the Demo

```bash
# From the repository root
cd intentusnet

# Install the package in development mode
pip install -e .

# Run the demo
python examples/canonical_demo/run.py
```

## Demo Phases

### Phase 1: Live Execution

The demo executes the maintenance power-off intent:

```
Executing intent: system.maintenance.poweroff
Targets: ['server', 'lights', 'cctv']

Result:
  Requested targets: ['server', 'lights', 'cctv']
  Allowed targets:   ['server', 'lights']
  Filtered targets:  ['cctv']
  All success:       True
```

The execution is recorded to `examples/canonical_demo/.demo_data/records/`.

### Phase 2: Crash Simulation & Recovery

The demo simulates a crash mid-execution:

1. **Execution starts** - WAL records `execution.started`
2. **Server step completes** - WAL records `step.started` and `step.completed`
3. **Lights step starts** - WAL records `step.started`
4. **CRASH** - Process terminates before `step.completed`

On restart, the `RecoveryManager`:
- Scans the WAL directory for incomplete executions
- Analyzes the execution state
- Determines which steps are complete vs incomplete
- Resumes execution from the incomplete step

```
Recovery analysis:
  Current state: in_progress
  Can resume: True
  Completed steps: ['poweroff-server']

Resuming execution...
  Skipping: poweroff-server (already completed)
  Completing: poweroff-lights (was interrupted)
  Skipping: poweroff-cctv (filtered as dangerous)
```

**Key guarantees:**
- Completed steps are NOT re-executed
- The filtered target (cctv) is NEVER executed
- Execution resumes deterministically

### Phase 3: Replay Demonstration

The demo replays the recorded execution:

```
Replaying execution: <execution_id>

Is replayable: True
Envelope hash match: True

Replayed response:
  (identical to original execution)
```

**Replay guarantees:**
- No routing decisions are made (uses recorded decisions)
- No agent code is executed (uses recorded outputs)
- Response is IDENTICAL to original execution
- Replay is DETERMINISTIC

## Files

```
examples/canonical_demo/
├── run.py      # Main demo script
├── agent.py    # Agent implementations
├── README.md   # This file
└── .demo_data/ # Generated at runtime
    ├── records/  # Execution recordings (JSON)
    └── wal/      # Write-ahead logs (JSONL)
```

## Agents

| Agent | Intent | Description |
|-------|--------|-------------|
| `maintenance-coordinator` | `system.maintenance.poweroff` | Orchestrates multi-target power operations |
| `server-power-agent` | `system.power.server` | Controls server power state |
| `lights-power-agent` | `system.power.lights` | Controls lighting systems |
| `cctv-power-agent` | `system.power.cctv` | Controls CCTV (filtered as dangerous) |

## Expected Output

```
======================================================================
  IntentusNet Canonical Demo
  Power Off System for Maintenance
======================================================================

This demo shows:
  1. Multi-target intent resolution with filtering
  2. WAL-based crash safety and recovery
  3. Deterministic execution recording and replay

======================================================================
  PHASE 1: LIVE EXECUTION
======================================================================

User Intent: "Power off system for maintenance"
Targets: ['server', 'lights', 'cctv']

Execution Result:
{
  "reason": "Power off system for maintenance",
  "requested_targets": ["server", "lights", "cctv"],
  "allowed_targets": ["server", "lights"],
  "filtered_targets": ["cctv"],
  "completed_steps": ["poweroff-server", "poweroff-lights"],
  "all_success": true
}

[VERIFICATION]
  [PASS] Target filtering verified - CCTV excluded as dangerous

======================================================================
  PHASE 2: CRASH SIMULATION & RECOVERY
======================================================================

[1] Starting execution with WAL...
[SIMULATED CRASH] Process terminated mid-execution!

[2] Process restarted - analyzing incomplete executions...
    Can resume: True
    Completed steps: ['poweroff-server']

[4] Resuming execution...
    SKIPPED: poweroff-cctv (filtered as dangerous)

======================================================================
  PHASE 3: REPLAY DEMONSTRATION
======================================================================

Is replayable: True
Replay is DETERMINISTIC

======================================================================
  DEMO COMPLETE
======================================================================

Summary:
  [PASS] Intent executed with multi-target resolution
  [PASS] Dangerous target (cctv) filtered and excluded
  [PASS] Allowed targets (server, lights) executed successfully
  [PASS] Crash simulated mid-execution
  [PASS] Recovery analyzed completed vs incomplete steps
  [PASS] Execution resumed deterministically
  [PASS] Filtered target (cctv) was NEVER executed
  [PASS] Recorded execution replayed deterministically

All demo requirements satisfied.
```

## Verifying Determinism

To verify determinism, run the demo multiple times:

```bash
python examples/canonical_demo/run.py
python examples/canonical_demo/run.py
python examples/canonical_demo/run.py
```

Each run will:
- Produce the same filtering decisions
- Execute the same agents in the same order
- Generate identical replay results

## Troubleshooting

**Import errors:**
```bash
# Ensure the package is installed
pip install -e .
```

**Permission errors:**
```bash
# Ensure the demo data directory is writable
rm -rf examples/canonical_demo/.demo_data
```

**Assertion errors:**
- The demo includes assertions that verify correct behavior
- If an assertion fails, it indicates a regression in the runtime
