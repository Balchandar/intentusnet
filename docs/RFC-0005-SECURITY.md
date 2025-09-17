# RFC-0005: EMCL Security Layer

## Status
Draft

## Abstract
This RFC defines the **Encrypted Model Context Layer (EMCL)** used in IntentusNet. EMCL ensures **confidentiality, integrity, and authentication** for intents exchanged between clients, gateways, routers, and agents.

---

## 1. EMCL Envelope

Every intent is wrapped in an EMCL envelope containing:

- `payload` → serialized intent JSON (can include qualifiers, metadata, etc.)
- `aes_iv` → initialization vector for AES encryption
- `hmac` → HMAC-SHA256 for integrity verification
- `signer` → agent or authority ID for signing
- `timestamp` → ISO8601 datetime

Example:

```json
{
  "payload": "<AES-encrypted-base64>",
  "aes_iv": "base64-iv",
  "hmac": "base64-hmac",
  "signer": "agent-1234",
  "timestamp": "2025-09-17T12:00:00Z"
}
```

---

## 2. Encryption & Integrity

- **AES-256-CBC** used to encrypt the `payload`.
- **HMAC-SHA256** computed over `payload + aes_iv` for integrity.
- Both AES and HMAC keys are derived using **PBKDF2** with a shared secret or agent GUID.

---

## 3. Signing & Verification

- Each agent can **sign** the EMCL envelope using its private key (or shared secret) to assert authenticity.
- Recipients verify:
  1. AES decryption succeeds.
  2. HMAC matches.
  3. Signature is valid and matches the `signer`.

---

## 4. Key Management

- Keys are rotated periodically via a **Key Vault**:
  - AES encryption keys
  - HMAC integrity keys
  - Signing keys
- Agents can retrieve keys securely using **JWT-authenticated requests** to the vault.
- EMCL supports **versioned keys** to maintain compatibility.

---

## 5. Security Principles

1. **Confidentiality**: Only authorized recipients can decrypt the intent payload.
2. **Integrity**: Any tampering triggers HMAC verification failure.
3. **Authentication**: Signer ID validated using registered keys.
4. **Forward Security**: Key rotation ensures past messages remain secure.
5. **Interoperability**: Compatible with MCP users if meta is preserved.

---

## 6. Example Flow

```mermaid
flowchart LR
    Client --> |EMCL Encrypt+Sign| Gateway
    Gateway --> Router --> Agent
    Agent --> |EMCL Response| Router --> Gateway --> Client
```

- Each message remains encrypted and signed throughout the flow.
- Tracer can log envelope metadata (timestamp, signer) without exposing payload.

---

## 7. EMCL Protocol Reference

For implementation details, sample code, and specifications, refer to the official EMCL protocol repository:

👉 [https://github.com/Balchandar/emcl-protocol](https://github.com/Balchandar/emcl-protocol)

---

## Notes

- EMCL is **required** for all IntentusNet messages.
- Optional metadata may be added inside `payload.meta` without affecting encryption.
- Fallback agents must verify envelope integrity before processing.

---

## Copyright
All text, diagrams, and specifications in this RFC are part of the IntentusNet project.
Copyright © 2025 Balachandar Manikandan.
Licensed under the MIT License.
