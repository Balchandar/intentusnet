# IntentusNet

### Deterministic Execution Runtime for Intent Routing and Multi-Agent Systems

**Deterministic • Transport-Agnostic • EMCL-Ready • MCP-Compatible**

---

[![Version](https://img.shields.io/badge/version-1.5.1-blue.svg)](#)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](#)
[![MCP](https://img.shields.io/badge/MCP-compatible-brightgreen)](#)
[![CI](https://img.shields.io/badge/CI-deterministic--safe-brightgreen)](#)
[![Architecture](https://img.shields.io/badge/architecture-execution--runtime-orange)](#)

---

## What's New in v1.5.1

IntentusNet v1.5.1 introduces **provable determinism** — the execution runtime now includes built-in mechanisms to verify, enforce, and prove that execution behavior is deterministic across runs, environments, and model swaps.

| Feature | Description |
|---------|-------------|
| **Execution Fingerprinting** | SHA-256 fingerprint of intent sequence, tool calls, param hashes, output hashes, retry pattern, and execution order |
| **Deterministic-Safe CI/CD** | 9-gate verification pipeline — determinism is enforced before deployment, not just tested |
| **Drift Detection** | Automatic detection of nondeterministic execution via fingerprint comparison |
| **WAL Replay Verification** | Prove that stored responses match original execution without re-running models |
| **Entropy Scanning** | Static analysis gate that blocks unseeded randomness, `uuid4()` in step IDs, and `time()` in fingerprints |
| **Project Blackbox Demo** | 8-act end-to-end demonstration proving all deterministic guarantees |

---

## Enterprise Features

IntentusNet includes enterprise-grade enforcement, federation, cryptographic proofs, and the Time Machine UI:

| Feature | Description |
|---------|-------------|
| **Gateway Enforcement** | Gateway as root of trust with mandatory signing |
| **Section Encryption** | EMCL section-level encryption with AAD binding |
| **Federation** | Cross-gateway verification and attestations |
| **Witness Gateways** | Independent verification with quorum enforcement |
| **Merkle Batches** | Cryptographic batching with inclusion proofs |
| **Transparency Logs** | Append-only public logs with signed checkpoints |
| **Compliance** | Jurisdiction-based enforcement with proofs |
| **Time Machine UI** | Read-only, verification-first execution inspection |

Enterprise Docs: [docs/enterprise/README.md](docs/enterprise/README.md)

---

IntentusNet is an open-source, language-agnostic **execution runtime for multi-agent and tool-driven systems**.
It makes routing, fallback, and failure handling **deterministic, recorded, explainable, and production-operable**.

IntentusNet focuses strictly on **execution semantics** (not planning, reasoning, or prompt intelligence) — ensuring that **execution behavior remains predictable even when models are not**.

---

## Documentation

Docs site: https://intentusnet.com

Start here:

- **Introduction** — what IntentusNet is (and isn't)
- **Guarantees** — the execution contract
- **Architecture** — routing, execution, recording
- **Determinism** — fingerprinting, drift detection, CI enforcement
- **CLI** — inspect, trace, retrieve, diff

---

## Quickstart

Install the Python runtime:

```bash
pip install intentusnet
```

Run a deterministic intent execution:

```python
from intentusnet.runtime import IntentRuntime
from intentusnet.intent import Intent

runtime = IntentRuntime.load_default()

result = runtime.execute(
    Intent(
        name="summarize_text",
        payload={"text": "Hello world"},
    )
)

print(result.output)
```

Inspect and retrieve the stored response (no model re-run):

```bash
intentusnet records list
intentusnet records show <execution-id>
intentusnet retrieve <execution-id>
```

---

## Deterministic MCP Gateway

Wrap **any** MCP server with the IntentusNet Gateway — zero changes to the server or client.

```
MCP Client  →  IntentusNet Gateway  →  Existing MCP Server
                      ↓
              WAL + Index + Data
```

### Why

MCP servers process tool calls but don't record them. When something goes wrong, there's no audit trail, no replay, and no way to prove what happened. The gateway adds these capabilities transparently.

### 5-Minute Example

**1. Start an MCP server** (included example):

```bash
python examples/basic-mcp-server/server.py
```

**2. Start the gateway:**

```bash
intentusnet gateway --http http://localhost:5123
```

**3. Send a request through the gateway:**

```bash
curl -s http://localhost:8765 -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"add","arguments":{"a":17,"b":25}}}' \
  | python -m json.tool
```

**4. List recorded executions:**

```bash
intentusnet executions
```

**5. Replay an execution** (WAL playback, no re-execution):

```bash
intentusnet replay <execution-id>
```

### Gateway CLI

| Command | Description |
|---------|-------------|
| `intentusnet gateway --wrap <cmd>` | Wrap a stdio MCP server |
| `intentusnet gateway --http <url>` | Proxy to an HTTP MCP server |
| `intentusnet replay <id>` | Fast replay from WAL |
| `intentusnet executions` | List all recorded executions |
| `intentusnet status` | Gateway status + WAL integrity |

### What Gets Recorded

Each tool call is persisted with: execution ID, deterministic seed, request/response hashes, WAL entries (execution start + end), timing metadata, and tool name.

### Current Limitations

- Streaming: simple pass-through (not recorded at stream level)
- No deterministic re-execution yet (replay returns stored response only)
- No undo or rollback
- No dashboard UI

Full documentation: [examples/basic-mcp-server/README.md](examples/basic-mcp-server/README.md)

---

## Why IntentusNet

Modern LLM systems are observable, but **not debuggable**.

In real production systems, failures are often:

- irreproducible
- incorrectly blamed on models
- hidden behind retries and fallback logic
- impossible to replay or audit

IntentusNet enforces **deterministic execution semantics around LLMs and tools**, so failures become:

- **Retrievable** — stored responses can be inspected without re-execution
- **Attributable** — routing decisions are recorded and traceable
- **Explainable** — execution paths are deterministic given identical input
- **Provable** — execution fingerprints verify determinism across runs

---

## Guarantees at a Glance

IntentusNet provides an explicit execution contract:

| Guarantee                    | Status                | Description                                      |
| ---------------------------- | --------------------- | ------------------------------------------------ |
| Deterministic Routing        | **Provided**          | Same input → same agent selection order          |
| Execution Recording          | **Provided**          | Every execution captured with stable hash        |
| Historical Response Retrieval| **Provided**          | Stored response returned, no model re-execution  |
| Policy Filtering             | **Provided**          | Partial allow/deny with continuation             |
| Structured Errors            | **Provided**          | Typed error codes, no silent failures            |
| Crash Recovery               | **Provided**          | WAL-backed execution state & recovery            |
| Signed WAL (REGULATED)       | **Provided**          | Ed25519 per-entry signatures for audit trail     |
| Execution Fingerprinting     | **Provided (v1.5.1)**   | SHA-256 fingerprint proves deterministic execution |
| Deterministic-Safe CI/CD     | **Provided (v1.5.1)**   | 9-gate pipeline enforces determinism before deploy |
| Drift Detection              | **Provided (v1.5.1)**   | Automatic nondeterminism detection via fingerprints |

Full guarantee details: https://intentusnet.com/docs/guarantees

---

## Provable Determinism (v1.5.1)

IntentusNet v1.5.1 treats determinism as a **provable property**, not just a design goal.

### Execution Fingerprinting

Every execution produces a SHA-256 fingerprint computed from:

- Intent sequence (ordered)
- Tool/agent call sequence
- Parameter hashes
- Output hashes
- Retry pattern
- Execution order
- Timeout values

**Same input + same runtime = same fingerprint.** If the fingerprint changes, something is nondeterministic — and the system detects it.

### Deterministic-Safe CI/CD

The CI/CD pipeline enforces determinism through 9 verification gates:

| Gate | Verification |
|------|-------------|
| Build Reproducibility | Two builds from same commit produce identical SHA-256 |
| Deterministic Execution | N runs of same intent produce identical fingerprints |
| WAL Replay Final-State | Replayed response matches original execution hash |
| Entropy Detection | Static scan blocks unseeded random, uuid4 in step IDs, time in hashes |
| Container Reproducibility | Container image hash is identical across builds |
| Routing Determinism | Same capabilities → same agent selection across N runs |
| Crash Recovery | Reversible steps resume; irreversible steps block safely |
| WAL Integrity & Tamper | Hash chain verification + tamper injection detection |
| Runtime Snapshot | Execution record survives JSON serialization round-trip |

**All 9 gates must pass before deployment.** A single failure blocks the release.

### Drift Detection

Inject a nondeterministic agent → fingerprint changes → drift detected → deployment blocked. This is not a test — it is a **runtime property** that is continuously enforced.

---

## Execution Recording & Historical Retrieval

IntentusNet treats **executions as immutable facts**, not transient logs.

Each execution is:

- recorded as a first-class artifact
- retrievable without re-running models (returns stored response)
- inspectable after crashes or upgrades

This enables:

- reliable root-cause analysis
- auditability (with signed WAL for REGULATED mode)
- safe model iteration without rewriting history

> **The model may change.**
> **The recorded execution remains intact.**

**Important:** "Retrieve" returns the stored response exactly as recorded. It does not re-execute agent code or validate that the current system would produce the same result.

This design is formalized in:
**RFC-0001 — Debuggable Execution Semantics for LLM Systems**
> `rfcs/RFC-0001-debuggable-llm-execution.md`

**Non-goals:** IntentusNet does not plan tasks, reason about goals, evaluate outputs, or optimize prompts.

---

## Core Capabilities

- Deterministic intent routing (DIRECT, FALLBACK, BROADCAST strategies)
- Explicit fallback chains
- Execution recording (**WAL-backed**, hash-chained)
- Execution fingerprinting (SHA-256, drift detection)
- Historical response retrieval
- Crash-safe recovery
- Typed failures & execution contracts
- Signed WAL entries (REGULATED mode, Ed25519)
- Compliance enforcement (DEVELOPMENT / STANDARD / REGULATED)
- EMCL payload encryption (AES-256-GCM)
- Deterministic-safe CI/CD (9-gate pipeline)
- Operator-grade CLI
- Transport-agnostic execution

---

## Intent-Oriented Routing

- Capability-driven routing
- Explicit fallback sequences
- Sequential or parallel execution
- Priority-based routing
- Auditable routing decisions
- Trace spans with execution metadata

Routing decisions are **deterministic and recorded**, not heuristic.

---

## EMCL Secure Envelope (Optional)

IntentusNet supports **EMCL (Encrypted Model Context Layer)**:

- AES-GCM authenticated encryption
- HMAC-SHA256 signing (demo provider)
- Identity-chain propagation
- Anti-replay protections

EMCL is optional and transport-agnostic.

---

## Compliance Modes

IntentusNet supports three compliance modes, enforced at router initialization:

| Mode          | Determinism | Signed WAL | PII Policy | Use Case                     |
| ------------- | ----------- | ---------- | ---------- | ---------------------------- |
| DEVELOPMENT   | Optional    | No         | No         | Local testing                |
| STANDARD      | Required    | No         | No         | Production (default)         |
| REGULATED     | Required    | Required   | Required   | HIPAA/SOC2/PCI-DSS workloads |

**REGULATED mode** requires:
- `require_determinism=True` (PARALLEL strategy blocked)
- Ed25519-signed WAL entries
- PII redaction policy configured

Configuration is validated at startup. Non-compliant configurations fail fast with explicit errors.

**Note:** IntentusNet is designed to support regulated workloads. Actual compliance certification depends on deployment configuration and organizational controls.

---

## MCP Compatibility

IntentusNet is **MCP-compatible by design**:

- Agents can be wrapped as MCP tools
- MCP tool requests can be accepted
- MCP-style responses can be emitted
- Optional EMCL-secured MCP envelopes

IntentusNet provides deterministic execution semantics **around MCP tools**, not a replacement for MCP.

MCP Documentation: https://intentusnet.com/docs/mcp

MCP Adapter Source: https://github.com/Balchandar/intentusnet/tree/main/src/intentusnet/mcp

---

## Language-Agnostic Design

Agents can be implemented in any language that supports:

- HTTP / JSON
- ZeroMQ
- WebSocket

Including: Python, C#, Go, TypeScript, Rust.

---

## SDK Status

### Included — Python Runtime SDK

- Intent router & fallback engine
- Agent base classes
- Agent registry
- Multi-transport execution
- Execution recorder & historical retrieval engine
- WAL-backed crash recovery
- Execution fingerprinting & drift detection
- Deterministic-safe CI/CD gates
- EMCL providers
- MCP adapter
- CLI tooling
- Example agents & demos

> **Note:** Higher-level ergonomic SDKs (decorators, auto-registration) and C#/TypeScript SDKs are planned next.

---

## Demos

All demos are runnable and deterministic. Execution responses are recorded and retrievable.

Demo Index: https://intentusnet.com/docs/demos

---

### `deterministic_routing_demo`

Compares three approaches using identical capabilities:

- **without** — ad-hoc production glue code
- **with** — deterministic routing via IntentusNet
- **mcp** — routing backed by a mock MCP tool server

Demo Documentation: https://intentusnet.com/docs/demos/deterministic-routing

Source Code: https://github.com/Balchandar/intentusnet/tree/main/examples/deterministic_routing_demo

```bash
python -m examples.deterministic_routing_demo.demo --mode without
python -m examples.deterministic_routing_demo.demo --mode with
python -m examples.deterministic_routing_demo.demo --mode mcp
```

---

### `execution_retrieval_example`

Demonstrates how model upgrades change live behavior while **past execution responses remain retrievable** without re-running models.

Demo Documentation: https://intentusnet.com/docs/demos/execution-replay

Source Code: https://github.com/Balchandar/intentusnet/tree/main/examples/execution_replay_example

---

### Project Blackbox (`superdemo`)

An 8-act end-to-end demonstration that proves every deterministic guarantee:

1. **Deterministic Execution** — identical intents produce identical fingerprints
2. **Replay Without Model** — historical response retrieval with zero re-execution
3. **Failure Traceability** — injected failure triggers deterministic fallback
4. **Cryptographic Verification** — Ed25519 signed WAL with tamper detection
5. **Crash Recovery** — reversible steps resume, irreversible steps block
6. **Model Swap Safety** — model upgrade preserves historical records
7. **EMCL Encryption** — AES-256-GCM authenticated encryption with tamper detection
8. **Deterministic Proof** — fingerprint stability, replay proof, drift detection

```bash
python -m examples.superdemo.demo
```

---

## Operational Scope (Important)

IntentusNet is a **deterministic execution runtime**, not an autonomous agent framework.

### Guarantees

- Deterministic routing, fallback, and failures
- Crash-safe execution recording (WAL with hash chaining)
- Historical response retrieval without re-execution
- Execution fingerprinting and drift detection
- Deterministic-safe CI/CD enforcement
- Explicit contracts and typed failures
- CLI-first operational control

### Explicit Non-Goals

- No task planning or reasoning
- No evaluation of model outputs
- No replacement for workflow engines
- No distributed consensus in v1

### Determinism Boundary

Determinism is enforced at the **execution layer**, not the **model layer**.
Non-deterministic model behavior is detected, recorded, and surfaced — never hidden.

---

## Roadmap

See [docs/roadmap.md](docs/roadmap.md) for the full roadmap.

**Current: v1.5.1** — Provable Determinism

- Execution fingerprinting
- Deterministic-safe CI/CD (9 gates)
- Drift detection
- Project Blackbox demo

**Next**

- Python ergonomic SDK
- C# SDK
- TypeScript SDK
- MCP adapter improvements
- EMCL key rotation

**Future (Optional)**

- Multi-agent planning layer (research)
- Trust-scored routing

---

## Author

**Balachandar Manikandan**

---

## License

MIT License

---

### Keywords

Deterministic execution runtime, intent routing, explicit fallback chains, recorded agent workflows, debuggable LLM systems, execution recording, WAL-backed recovery, signed WAL, compliance modes, MCP-compatible runtime, EMCL-secured agent communication, transport-agnostic AI infrastructure, execution fingerprinting, deterministic CI/CD, drift detection, provable determinism.
