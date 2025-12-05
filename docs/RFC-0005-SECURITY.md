# RFC-0005 — Security Model for IntentusNet

## Status
**Draft — v1.0**

## Purpose
This RFC defines the security principles, threat model, and protective mechanisms used within **IntentusNet**, including EMCL optional encryption, identity chain, authentication, agent trust levels, and secure routing guarantees.

---

# 1. Security Philosophy

IntentusNet is designed for:
- **Language-agnostic agents**
- **Distributed execution**
- **Plug‑and‑play transports**
- **Optional encryption (EMCL)**

The security model must therefore support:
1. **Zero-trust execution between agents**
2. **Message integrity & provenance**
3. **Confidentiality when required**
4. **Replay protection**
5. **Pluggable authentication**
6. **Transport‑independent guarantees**

Security is **optional but strongly encouraged** for regulated domains.

---

# 2. Threat Model

## 2.1 Threat Actors
| Actor | Description |
|------|-------------|
| Malicious external user | Attempts to intercept or alter data |
| Compromised agent | Misbehaves or impersonates another agent |
| Compromised network | MITM attacks between agents/services |
| Rogue service | Unauthorized service calling IntentusNet runtime |
| Replay attacker | Reuses intercepted encrypted payloads |

---

# 3. Security Layers

IntentusNet uses a **layered model**:

```
Layer 5: Agent Logic / Orchestration (L5)
Layer 4: Routing Rules / Priority / Failover (L4)
Layer 3: Agent Registry & Identity (L3)
Layer 2: EMCL Encryption & Signing (L2)
Layer 1: Transport (HTTP, ZMQ, MCP, WebSocket) (L1)
```

Only L2 (EMCL) provides **cryptographic guarantees**.

---

# 4. EMCL: Optional Secure Envelope (L2)

When enabled, **EMCL** provides:

## 4.1 Encryption (AES-GCM)
- Symmetric 256-bit AES-GCM
- Nonce-based encryption
- High-speed, low-latency
- Payload confidentiality

## 4.2 Integrity via HMAC
- HMAC-SHA256 signatures
- Ensures no tampering
- Validates message origin

## 4.3 Identity Chain
A cryptographically signed lineage:

```
Client → Orchestrator → AgentA → AgentB
```

Used for:
- Auditing
- Access decisions
- Traceability

## 4.4 Replay Protection
Every envelope includes:
- `nonce`
- `timestamp`
- optional `exp` / `ttl`

---

# 5. Agent Identity & Trust Model (L3)

Each agent has:

```json
{
  "agentId": "summarizer.v1",
  "roles": ["compute", "llm"],
  "trustLevel": "high",
  "signingKeyId": "key-001"
}
```

### 5.1 Trust Levels
| Level | Meaning |
|-------|---------|
| **high** | Full workloads permitted |
| **medium** | Some restricted intents |
| **low** | Only non-sensitive operations |
| **untrusted** | Sandboxed or synthetic output only |

Routing layer **may refuse** execution based on trust.

---

# 6. Secure Routing Rules (L4)

Routing decisions consider:

1. **Priority**
2. **Trust level**
3. **Fallback chain**
4. **Agent health**
5. **Capabilities**
6. **Intent constraints**

A router may reject an agent if:

- Trust level is insufficient  
- Agent identity does not match expected roles  
- EMCL identity chain is broken  
- Request is expired  

---

# 7. Secure Transport Requirements (L1)

Supported transports:
- HTTP + TLS
- ZeroMQ CURVE (optional)
- WebSocket Secure (WSS)
- MCP secure channels

Each transport **may** apply its own cryptographic layer.  
IntentusNet treats EMCL as **end‑to‑end**, above transport.

---

# 8. Authentication & Authorization

IntentusNet does not force a specific system but provides hooks.

## 8.1 Supported Models
- API keys
- JWTs (access / identity tokens)
- mTLS
- HMAC shared secrets
- Custom auth pipeline

## 8.2 Pluggable Auth Gate
Before processing any intent:

```
AuthGate.validate(request)
```

Provided as extension point.

---

# 9. Logging & Security Auditing

Every routed intent can produce:

- Trace spans  
- Identity chain  
- Routing decisions  
- Errors  
- Fallback transitions  

These support:
- SIEM integration
- SOC2 evidence
- HIPAA audit trails

---

# 10. Example EMCL Envelope

```json
{
  "emclVersion": "1.0",
  "ciphertext": "...",
  "nonce": "...",
  "hmac": "...",
  "identityChain": [
    "client:user123",
    "runtime:orch",
    "agent:summarizer.v1"
  ]
}
```

---

# 11. Security Recommendations

### When to enable EMCL:
- PII/PHI workloads
- HIPAA/PCI regulated use
- Multi-tenant environments
- Edge → cloud transmission

### When plaintext is acceptable:
- Controlled internal networks
- Synthetic or non-sensitive data
- Local debugging

---

# 12. Future Work

| Feature | Status |
|---------|--------|
| EMCL Key Vault | NEXT VERSION |
| Agent attestation (signing certs) | FUTURE |
| Distributed trust federation | FUTURE |
| Agent-level RBAC | FUTURE |
| Secure enclaves | FUTURE |

---

# 13. Summary

IntentusNet provides a **practical, layered, optional security model** that adapts to:

- Lightweight internal systems  
- Enterprise-grade regulated workloads  
- Mixed-language multi-agent architectures  
- High-speed orchestrator pipelines  

Security is **never forced**, but always available.

Implementation Status:
- Core Features: Implemented
- Extended Features: Roadmap (not yet available)
