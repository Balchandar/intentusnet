# Gateway Enforcement

The gateway is the **root of trust** in IntentusNet Enterprise. It is responsible for:

- Canonical execution construction
- Mandatory gateway signing
- Mandatory encryption enforcement
- Policy-based admission control
- Replay enforcement with parentExecutionHash

## Critical Invariant

**Agents MUST NOT generate final execution records.**

Only the gateway constructs `CanonicalExecutionEnvelope` instances. This ensures:
- Consistent signing by a trusted entity
- Enforcement of encryption policies
- Validation of replay chains
- Audit trail integrity

## Gateway Identity

Every gateway has a cryptographic identity using Ed25519:

```python
@dataclass(frozen=True)
class GatewayIdentity:
    gateway_id: str           # Unique identifier
    key_id: str               # SHA-256 fingerprint (first 16 chars)
    public_key_bytes: bytes   # Raw Ed25519 public key (32 bytes)
    domain: Optional[str]     # Domain for federation
    created_at: str           # ISO 8601 timestamp
```

## Canonical Execution Envelope

The canonical execution envelope is the only valid representation of an execution:

```python
@dataclass
class CanonicalExecutionEnvelope:
    execution_id: str          # UUID
    canonical_hash: str        # SHA-256 of content
    gateway_id: str            # Creator gateway
    created_at: str            # ISO 8601
    parent_execution_hash: Optional[str]  # Replay lineage

    intent_name: str
    intent_version: str

    input: Dict[str, Any]      # May be encrypted
    output: Optional[Dict[str, Any]]
    trace: Optional[List[Dict[str, Any]]]
    metadata: Dict[str, Any]

    input_encrypted: bool
    output_encrypted: bool
    trace_encrypted: bool

    gateway_signature: GatewaySignature  # Ed25519
```

## Admission Policies

The gateway evaluates admission policies before creating executions:

```python
class AdmissionPolicy:
    def evaluate(
        self,
        intent_name: str,
        payload: Dict[str, Any],
        source_agent: Optional[str],
        parent_execution_hash: Optional[str],
        context: Dict[str, Any],
    ) -> AdmissionResult
```

### Built-in Policies

| Policy | Purpose |
|--------|---------|
| `AllowAllPolicy` | Development only - allows all |
| `IntentAllowlistPolicy` | Only allows specified intents |
| `AgentTrustPolicy` | Requires trusted source agents |
| `ReplayChainPolicy` | Enforces replay chain integrity |
| `WitnessRequiredPolicy` | Requires witness attestation |
| `CompositeAdmissionPolicy` | Combines multiple policies |

### Policy Evaluation

1. Policies are evaluated in order
2. First `DENY` terminates evaluation
3. `REQUIRE_WITNESS` is accumulated
4. Only if all pass is execution allowed

## Encryption Enforcement

```python
encryption_requirement: str  # "none", "optional", "mandatory"
```

When `mandatory`:
- Input MUST be encrypted
- Output MUST be encrypted
- Trace MUST be encrypted

Violation raises `EncryptionPolicyError`.

## Replay Chain Validation

For executions with `parent_execution_hash`:

1. Parent hash format is validated
2. Parent existence is verified (in production, from store)
3. Chain integrity is preserved

Violation raises `ReplayViolationError`.

## Usage Example

```python
from intentusnet.phase2.gateway import (
    GatewayEnforcer,
    GatewayConfig,
    GatewaySigner,
    IntentAllowlistPolicy,
    AgentTrustPolicy,
)

# Create signer (use HSM in production)
signer = GatewaySigner.generate()

# Configure policies
policies = [
    IntentAllowlistPolicy({"process_document", "query_data"}),
    AgentTrustPolicy({"agent-001", "agent-002"}),
]

# Configure gateway
config = GatewayConfig(
    gateway_id="gateway-001",
    domain="gateway.example.com",
    encryption_requirement="mandatory",
    admission_policies=policies,
    require_replay_chain=True,
)

# Create enforcer
enforcer = GatewayEnforcer(config, signer)

# Evaluate admission
result = enforcer.evaluate_admission(
    intent_name="process_document",
    payload={"doc_id": "123"},
    source_agent="agent-001",
)

# Construct envelope
envelope = enforcer.construct_envelope(
    intent_name="process_document",
    intent_version="1.0",
    input_payload=encrypted_input,
    output_payload=encrypted_output,
    trace=encrypted_trace,
    metadata={"agent": "agent-001"},
    input_encrypted=True,
    output_encrypted=True,
    trace_encrypted=True,
)

# Verify
assert enforcer.verify_envelope(envelope)
```

## Signature Verification

Verification is offline-capable:

```python
class GatewayVerifier:
    def add_identity(self, identity: GatewayIdentity) -> None
    def verify_envelope(self, envelope: CanonicalExecutionEnvelope) -> bool
```

Verification checks:
1. Canonical hash matches content
2. Gateway signature is valid

## Security Considerations

1. **Private Key Protection**: Use HSM or KMS
2. **Key Rotation**: Supported via `key_id`
3. **Policy Order**: Place most restrictive policies first
4. **Audit Logging**: Log all admission decisions
