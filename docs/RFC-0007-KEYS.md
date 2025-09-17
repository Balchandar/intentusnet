# RFC-0007: IntentusNet Key Vault & Key Rotation

## Status
Draft

## Abstract
This RFC defines the **Key Vault** and key rotation mechanism for IntentusNet, ensuring secure encryption, integrity, and signing for EMCL and intent messages.

---

## 1. Key Types

IntentusNet uses three main types of keys:

1. **AES Keys** – for encrypting EMCL payloads (AES-256-CBC).
2. **HMAC Keys** – for integrity verification (HMAC-SHA256).
3. **Signing Keys** – for authenticating the EMCL envelope (RSA/ECDSA or shared secret).

---

## 2. Key Vault

- Centralized or distributed secure storage for all keys.
- Accessible via **JWT-authenticated requests**.
- Provides **versioned keys** for backward compatibility.
- Logs all key access for auditing.

---

## 3. Key Rotation

- Keys must be rotated periodically:
  - **AES** – every 90 days
  - **HMAC** – every 90 days
  - **Signing keys** – every 180 days
- Rotation steps:
  1. Generate new key.
  2. Publish version and make active.
  3. Maintain old key versions for decrypting older messages.
  4. Update registry and notify authorized agents.

---

## 4. Versioning

- Every key is versioned (e.g., `AES-v3`, `HMAC-v2`, `SIGN-v1`).
- EMCL envelope includes **key version** metadata.
- Agents use the versioned key corresponding to the envelope’s metadata.

Example:

```json
{
  "payload": "<AES-encrypted-base64>",
  "aes_iv": "base64-iv",
  "key_version": "AES-v3",
  "hmac": "base64-hmac",
  "signer": "agent-1234",
  "timestamp": "2025-09-17T12:00:00Z"
}
```

---

## 5. Access Control

- Only authorized agents or services can request keys.
- JWT contains:
  - `agent_id`
  - `roles`
  - `permissions`
- Vault verifies JWT and enforces least-privilege access.

---

## 6. Fallback & Compatibility

- Older key versions remain valid until no active messages use them.
- Vault must allow **decryption with old keys** but only encrypt with active keys.
- Ensures smooth rotation without breaking ongoing intents.

---

## 7. Security Principles

1. **Confidentiality**: Keys are never exposed in plaintext outside vault.
2. **Auditability**: All key usage is logged.
3. **Forward Security**: Rotated keys prevent compromise of future messages.
4. **Backward Compatibility**: Older messages can still be decrypted for auditing or reprocessing.

---

## Notes

- Key rotation schedule may be adjusted based on operational risk.
- Vault integration should be resilient, with retries and fallback endpoints.
- Optional: integrate with hardware security modules (HSMs) for added security.

---

## Copyright
All text, diagrams, and specifications in this RFC are part of the IntentusNet project.
Copyright © 2025 Balachandar Manikandan.
Licensed under the MIT License.
