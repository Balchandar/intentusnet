# IntentusNet Enterprise: Enforcement, Federation, Proofs & Time Machine

Enterprise features build on the core runtime foundation to provide:

- **Gateway Enforcement**: Gateway as root of trust with mandatory signing
- **EMCL Encryption**: Section-level encryption with AAD binding
- **Gateway Federation**: Cross-gateway verification and attestations
- **Witness Gateways**: Independent verification with quorum enforcement
- **Merkle Batches**: Cryptographic batching with inclusion proofs
- **Transparency Logs**: Append-only public logs with signed checkpoints
- **Regulator Compliance**: Jurisdiction-based compliance enforcement
- **Time Machine UI**: Read-only, verification-first execution inspection

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Gateway Enforcer                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│  │  Admission  │  │  Canonical  │  │  Encryption │                  │
│  │   Policy    │  │  Execution  │  │  Enforcer   │                  │
│  └─────────────┘  └─────────────┘  └─────────────┘                  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Section-Level Encryption                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│  │   Input     │  │   Output    │  │   Trace     │                  │
│  │  AES-256    │  │  AES-256    │  │  AES-256    │                  │
│  │    GCM      │  │    GCM      │  │    GCM      │                  │
│  └─────────────┘  └─────────────┘  └─────────────┘                  │
│                    AAD: executionId + canonicalHash + signerId       │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Merkle Batching                              │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │  Execution₁  Execution₂  Execution₃  ...  Executionₙ   │        │
│  │      │           │           │                │         │        │
│  │      ▼           ▼           ▼                ▼         │        │
│  │   Leaf₁       Leaf₂       Leaf₃           Leafₙ        │        │
│  │      └───────┬───┘           └───────┬───────┘         │        │
│  │              │                       │                  │        │
│  │           Hash₁₂                  Hash₃ₙ               │        │
│  │              └───────────┬───────────┘                  │        │
│  │                          │                              │        │
│  │                     Batch Root                          │        │
│  └─────────────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Transparency Log                                │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │  Batch₁  Batch₂  Batch₃  ...  Batchₙ                    │        │
│  │    │       │       │            │                        │        │
│  │    ▼       ▼       ▼            ▼                        │        │
│  │  Entry₁  Entry₂  Entry₃      Entryₙ                     │        │
│  │    └───┬───┘       └────┬─────┘                         │        │
│  │        │                │                                │        │
│  │     Hash₁₂           Hash₃ₙ                             │        │
│  │        └────────┬───────┘                               │        │
│  │                 │                                        │        │
│  │            Log Root ──► Signed Checkpoint               │        │
│  └─────────────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Time Machine UI                                 │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐       │
│  │  Timeline  │ │   Detail   │ │   Trace    │ │   Proofs   │       │
│  │    View    │ │    View    │ │   Viewer   │ │   Export   │       │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘       │
│                                                                      │
│  CRITICAL: Verification-First - Signature MUST verify before render │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Invariants

### Gateway Enforcement
1. Gateway is the ONLY entity that constructs canonical execution envelopes
2. All executions MUST be signed by the gateway
3. Encryption is MANDATORY per policy
4. Agents MUST NOT generate final execution records
5. Replay enforcement requires valid parentExecutionHash chain

### EMCL Encryption
1. Signature MUST be verified before ANY decryption attempt
2. Decryption is ALWAYS explicit - never auto-decrypt
3. AAD binds ciphertext to execution context
4. Each section can have independent encryption state

### Transparency
1. Log is append-only - entries cannot be modified or removed
2. Checkpoints are signed by the log operator
3. All proofs are offline-verifiable

### Time Machine UI
1. Read-only by default
2. No silent failures
3. Verification status ALWAYS shown first
4. Decryption must be explicit and user-triggered

## Documentation Index

- [Gateway Enforcement](./gateway-enforcement.md)
- [EMCL Section Encryption](./emcl-encryption.md)
- [Gateway Federation](./federation.md)
- [Witness Gateways](./witness.md)
- [Merkle Batches](./merkle-batches.md)
- [Transparency Logs](./transparency-logs.md)
- [Regulator Compliance](./regulator-compliance.md)
- [Time Machine UI](./time-machine-ui.md)

## Core vs Enterprise Comparison

| Aspect | Core Runtime | Enterprise Features |
|--------|--------------|---------------------|
| Execution Creation | Agents create records | Gateway creates canonical records |
| Signing | Optional WAL signing | Mandatory gateway signing |
| Encryption | Transport-level | Section-level with AAD |
| Verification | Local | Cross-gateway with witnesses |
| Batching | None | Merkle-rooted batches |
| Transparency | None | Append-only public logs |
| Compliance | Config-based | Jurisdiction-based with proofs |
| UI | None | Verification-first Time Machine |

## Getting Started

```python
from intentusnet.phase2 import (
    GatewayEnforcer,
    GatewayConfig,
    GatewaySigner,
    SectionEncryptor,
    SectionEncryptionConfig,
    TimeMachineAPI,
)

# Create gateway signer (use HSM in production)
signer = GatewaySigner.generate()

# Configure gateway
config = GatewayConfig(
    gateway_id="gateway-001",
    domain="gateway.example.com",
    encryption_requirement="mandatory",
)

# Create enforcer
enforcer = GatewayEnforcer(config, signer)

# Create canonical execution
envelope = enforcer.construct_envelope(
    intent_name="process_document",
    intent_version="1.0",
    input_payload={"document_id": "doc-123"},
    output_payload={"status": "processed"},
    trace=[{"type": "step", "name": "parse"}],
    metadata={"agent": "processor"},
    input_encrypted=True,
    output_encrypted=True,
    trace_encrypted=True,
)

# Verify execution
assert enforcer.verify_envelope(envelope)
```

## Security Considerations

1. **Private Keys**: Use HSM or KMS for production signing keys
2. **Key Rotation**: Use key_id for seamless rotation
3. **AAD Binding**: Never skip AAD verification during decryption
4. **Witness Quorum**: Configure appropriate quorum for your risk tolerance
5. **SLA Monitoring**: Monitor publication SLAs actively
