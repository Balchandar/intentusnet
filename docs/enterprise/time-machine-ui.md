# Time Machine UI

The Time Machine UI is a **read-only, verification-first** system for execution inspection.

## Critical Constraints

1. **Read-only by default** - Never mutates history
2. **No silent failures** - All errors are surfaced
3. **No protocol shortcuts** - Follows all enterprise contracts
4. **UI consumes backend contracts exactly** - No data invention
5. **Verification status ALWAYS shown first**
6. **Signature MUST verify before rendering content**
7. **Decryption must be explicit and user-triggered**
8. **Never auto-decrypt**

## Components

### 1. Timeline View

Paginated execution timeline with filtering.

```python
from intentusnet.phase2.timemachine.ui import TimelineView
from intentusnet.phase2.timemachine.api import TimeMachineAPI

api = TimeMachineAPI(gateway_verifier)
timeline = TimelineView(api)

# Load timeline
state = timeline.load(
    filter_params=TimelineFilter(intent_names={"process_document"}),
    page=0,
    page_size=50,
)

# Navigate
timeline.next_page()
timeline.previous_page()

# Filter
timeline.apply_filter(
    intent_names={"query_data"},
    status={VerificationStatus.VERIFIED},
)
```

Features:
- ExecutionId always visible
- Parent/child lineage indicators
- Filter by intent, gateway, status
- Pagination with configurable page size

### 2. Execution Detail View

Detailed execution view with tabs.

```python
from intentusnet.phase2.timemachine.ui import ExecutionDetailView

detail = ExecutionDetailView(api)
state = detail.load(execution_id)

# Verification banner ALWAYS shown first
banner = state.verification_banner
if banner.status != VerificationStatus.VERIFIED:
    # Show warning
    pass

# Switch tabs
detail.switch_tab(DetailTab.TRACE)

# Explicit decryption (requires user action)
if state.input_section.can_decrypt:
    section = detail.request_decryption(
        section_type=SectionType.INPUT,
        dek=user_provided_dek,
    )
```

Tabs:
- Summary - Execution overview
- Input - Input payload (may be encrypted)
- Output - Output payload (may be encrypted)
- Trace - Execution trace
- Diff - Comparison with other executions
- Metadata - Execution metadata
- Witnesses - Witness attestations
- Batches - Batch membership
- Compliance - Regulatory status

### 3. Trace Viewer

Deterministic tree rendering of execution traces.

```python
from intentusnet.phase2.timemachine.ui import TraceViewer

viewer = TraceViewer()
state = viewer.load_trace(execution_id, trace_data)

# Tree navigation
viewer.toggle_node(node_id)
viewer.select_node(node_id)
viewer.expand_all()
viewer.collapse_all()

# Get flattened list for rendering
visible_nodes = viewer.get_flattened_nodes()
```

Features:
- Collapsible nodes
- Timing per node
- Hash-based identity per node
- Deterministic rendering

### 4. Diff Viewer

Structural diff visualization.

```python
from intentusnet.phase2.timemachine.ui import DiffViewer

diff = DiffViewer()
state = diff.compute_diff(
    old_execution_id=old_id,
    new_execution_id=new_id,
    old_data=old_data,
    new_data=new_data,
    old_hash_verified=True,  # REQUIRED
    new_hash_verified=True,  # REQUIRED
)

# Select section to view
diff.select_section(DiffSection.INPUT)

# Toggle unchanged entries
diff.toggle_show_unchanged()

# Get summary
summary = diff.get_summary()
```

**Note**: Diff only computed if BOTH executions have verified hashes.

### 5. Witness & Federation View

Visualization of witness attestations.

```python
from intentusnet.phase2.timemachine.ui import WitnessView

witness = WitnessView()
state = witness.load(
    execution_id=execution_id,
    source_gateway_id=gateway_id,
    attestations=attestations,
    quorum=quorum,
)

# View scope coverage
coverage = witness.get_scope_coverage()

# View summary
summary = witness.get_witness_summary()
```

Features:
- Source gateway info
- Witness attestations with scope details
- Quorum state visualization
- Trust level indicators

### 6. Batch & Transparency View

Merkle batch and transparency log visualization.

```python
from intentusnet.phase2.timemachine.ui import BatchView

batch_view = BatchView()
state = batch_view.load(
    execution_id=execution_id,
    batch=batch,
    batch_proof=batch_proof,
    log_proof=log_proof,
    checkpoint=checkpoint,
    compliance_package=compliance_package,
)

# Verify proofs
batch_valid = batch_view.verify_batch_proof()
log_valid = batch_view.verify_log_proof()

# Get verification summary
summary = batch_view.get_verification_summary()
```

Features:
- Batch membership info
- Inclusion proof visualization
- Transparency log status
- Compliance status and SLA timing

### 7. Proof Exporter

Export proof bundles for offline verification.

```python
from intentusnet.phase2.timemachine.ui import ProofExporter, ExportOptions

exporter = ProofExporter(api)

# Configure export
options = ExportOptions(
    format=ExportFormat.JSON,
    include_witness_attestations=True,
    include_batch_proof=True,
    include_log_proof=True,
    pretty_print=True,
)

# Export
result = exporter.export(execution_id, options)

if result.success:
    # Save to file
    with open(result.filename_suggestion, "w") as f:
        f.write(result.data)

# Verify exported proof
verification = exporter.verify_export(
    data=exported_data,
    format=ExportFormat.JSON,
)
```

Export includes:
- Execution canonical hash
- Gateway signatures
- Witness attestations
- Batch inclusion proof
- Transparency log inclusion proof
- Verification metadata

## API Backend

The `TimeMachineAPI` provides the backend for all UI components:

```python
from intentusnet.phase2.timemachine.api import (
    TimeMachineAPI,
    ExecutionQuery,
    TimelineFilter,
    PaginationParams,
)

api = TimeMachineAPI(
    gateway_verifier=verifier,
    section_encryptor=encryptor,
    batch_verifier=batch_verifier,
)

# Store executions (for testing)
api.store_execution(envelope, encrypted_payload, dek)

# Query timeline
entries, total = api.query_timeline(
    filter_params=TimelineFilter(...),
    pagination=PaginationParams(...),
)

# Get execution detail
detail = api.get_execution_detail(ExecutionQuery(execution_id))

# Request decryption (explicit)
result = api.request_decryption(
    execution_id=execution_id,
    section_type=SectionType.INPUT,
    dek=dek,
)

# Export proof bundle
bundle = api.export_proof_bundle(execution_id)

# Verify execution
checks = api.verify_execution(execution_id)
```

## Security Model

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interface                          │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           VERIFICATION BANNER (Always First)        │   │
│  │  ✓ Verified  |  ⚠ Partial  |  ✗ Failed             │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                 │
│                           ▼                                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  Content Area                        │   │
│  │                                                      │   │
│  │   [Encrypted Section]  ──► [Decrypt] Button         │   │
│  │                             (Explicit Action)        │   │
│  │                                                      │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

Key security features:
1. Verification status is computed and displayed before any content
2. Encrypted sections show lock icon with explicit decrypt button
3. Decryption requires user action (button click)
4. Verification failure blocks decryption
5. All proof verifications are displayed clearly
