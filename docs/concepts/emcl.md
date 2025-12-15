# EMCL (Encrypted Model Context Layer) — IntentusNet v1

This document explains **EMCL support in IntentusNet v1**: what it is, what it does,
and—equally important—what it does **not** do.

EMCL is an **optional transport-layer security mechanism**. Routing behavior is unchanged
whether EMCL is enabled or not.

---

## What EMCL Is

EMCL (Encrypted Model Context Layer) is a protocol wrapper used to:

- Encrypt intent payloads over transports
- Protect payload integrity
- Preserve agent identity chains across hops

EMCL operates **below routing** and **above transport framing**.

---

## What EMCL Is Not

EMCL is **not**:

- An authentication system
- An authorization framework
- A policy engine
- A key-management service
- A replacement for TLS

It protects message contents, not system boundaries.

---

## Where EMCL Fits

The execution stack with EMCL enabled looks like:

```text
IntentEnvelope
   ↓
(EMCL encrypt)
   ↓
TransportEnvelope
   ↓
Transport
   ↓
(EMCL decrypt)
   ↓
IntentEnvelope
   ↓
Router
```

The router **never sees encrypted data**.

---

## EMCL Providers

IntentusNet v1 supports pluggable EMCL providers.

An EMCL provider must implement:

```python
class EMCLProvider(Protocol):
    def encrypt(self, body: Dict[str, Any]) -> EMCLEnvelope:
        ...

    def decrypt(self, envelope: EMCLEnvelope) -> Dict[str, Any]:
        ...
```

The router is unaware of the provider implementation.

---

## Supported Providers in v1

### Simple HMAC Provider

Characteristics:

- HMAC-SHA256 signing
- No real encryption (plaintext payload)
- Intended for demos and testing only

This provider exists to validate protocol flow, not security.

---

### AES-GCM Provider

Characteristics:

- AES-256-GCM authenticated encryption
- Random nonce per message
- Authenticated integrity via GCM tag
- Optional identity chain propagation

This is the **production-grade EMCL provider**.

---

## Identity Chain

EMCL supports an optional **identity chain**:

- Each hop may append its identity
- Ordering is preserved
- Chain represents provenance, not authorization

Identity chains are:

- Informational
- Append-only
- Not validated in v1

---

## Error Handling

If EMCL validation fails:

- Decryption errors are raised inside the transport
- The transport converts them into `TRANSPORT_ERROR`
- Routing is not attempted

EMCL failures never reach agent logic.

---

## Determinism and EMCL

EMCL does not affect determinism:

- Routing decisions remain unchanged
- Agent selection is identical
- Fallback behavior is preserved

Only payload confidentiality changes.

---

## Operational Considerations

When enabling EMCL:

- Key management is the responsibility of the host system
- Keys must be rotated externally
- Transport timeouts still apply

EMCL increases CPU cost due to encryption.

---

## Design Rationale

EMCL is optional to ensure:

- Minimal v1 runtime
- Clear separation of concerns
- No forced security assumptions

Security layers should be composable, not mandatory.

---

## Summary

In IntentusNet v1, EMCL:

- Encrypts payloads at transport boundaries
- Preserves routing semantics
- Adds confidentiality without altering execution

It is a **security layer**, not a control plane.
