# EMCL Section-Level Encryption

IntentusNet Enterprise provides section-level encryption with cryptographic binding to execution context.

## Key Features

- **Section-Level Granularity**: Input, Output, Trace, Metadata.custom
- **AES-256-GCM**: Authenticated encryption
- **Per-Execution DEK**: Unique data encryption key per execution
- **Optional KEK Wrapping**: Key encryption key for secure storage
- **AAD Binding**: Ciphertext bound to executionId + canonicalHash + signerId
- **Signature-First**: Verification BEFORE decryption

## Critical Invariants

1. **Signature MUST be verified before ANY decryption attempt**
2. **Decryption is ALWAYS explicit - never auto-decrypt**
3. **AAD binds ciphertext to execution context**
4. **Each section can have independent encryption state**

## Data Encryption Key (DEK)

Each execution gets a unique 256-bit DEK:

```python
@dataclass(frozen=True)
class ExecutionDEK:
    execution_id: str    # Owning execution
    key_bytes: bytes     # 32 bytes (256 bits)
    key_id: str          # SHA-256 fingerprint
    created_at: str      # ISO 8601
```

### DEK Generation

```python
# Random generation
dek = ExecutionDEK.generate(execution_id)

# Deterministic derivation
dek = ExecutionDEK.derive(
    execution_id=execution_id,
    master_secret=secret_bytes,
    salt=salt_bytes,
)
```

## Key Encryption Key (KEK)

DEKs can be wrapped with a KEK for secure storage:

```python
kek_store = KEKStore()
kek_store.add_kek("kek-001", kek_bytes)

# Wrap DEK
wrapper = kek_store.wrap_dek(dek, "kek-001")

# Unwrap DEK
dek = kek_store.unwrap_dek(wrapper, execution_id)
```

## AAD Binding

Associated Authenticated Data prevents:
- Moving ciphertext between executions
- Substituting sections
- Replay attacks

```python
aad = {
    "executionId": "...",
    "canonicalHash": "...",
    "signerId": "...",
    "sectionType": "input"
}
```

## Section Encryption

```python
from intentusnet.phase2.gateway.encryption import (
    SectionEncryptor,
    SectionType,
    SectionEncryptionConfig,
    ExecutionDEK,
)

encryptor = SectionEncryptor()

# Generate DEK
dek = ExecutionDEK.generate(execution_id)

# Encrypt section
encrypted = encryptor.encrypt_section(
    section_type=SectionType.INPUT,
    plaintext={"document_id": "doc-123"},
    execution_id=execution_id,
    canonical_hash=canonical_hash,
    signer_id=gateway_key_id,
    dek=dek,
)
```

## Section Decryption

**CRITICAL: Signature must be verified first!**

```python
from intentusnet.phase2.gateway.encryption import (
    DecryptionRequest,
)

# Create request with verified flag
request = DecryptionRequest(
    execution_id=execution_id,
    section_type=SectionType.INPUT,
    signature_verified=True,  # MUST be True
    dek=dek,
)

# Validate request (raises if not verified)
request.validate()

# Decrypt
result = encryptor.decrypt_section(section, request)

if result.success:
    plaintext = result.plaintext
else:
    error = result.error
```

## Encryption Configuration

```python
config = SectionEncryptionConfig(
    encrypt_input=True,
    encrypt_output=True,
    encrypt_trace=True,
    encrypt_metadata_custom=False,
    use_kek_wrapping=True,
    kek_id="kek-001",
)
```

## Full Execution Encryption

```python
payload, dek = encryptor.encrypt_execution(
    execution_id=execution_id,
    canonical_hash=canonical_hash,
    signer_id=signer_id,
    input_payload={"data": "..."},
    output_payload={"result": "..."},
    trace=[{"type": "step", "name": "process"}],
    metadata_custom=None,
    config=config,
)
```

## EncryptedSection Structure

```python
@dataclass
class EncryptedSection:
    section_type: str           # "input", "output", etc.
    ciphertext: str             # Base64-encoded
    iv: str                     # Base64-encoded nonce
    aad_components: Dict        # AAD parameters
    dek_id: str                 # DEK identifier
    kek_wrapper: Optional[KEKWrapper]  # Wrapped DEK
```

## Security Considerations

1. **Never Skip Verification**: Always verify signature before decryption
2. **Explicit Decryption**: UI must require user action to decrypt
3. **DEK Protection**: Store DEKs securely (HSM, KMS, or wrapped with KEK)
4. **Nonce Uniqueness**: Each encryption uses random 96-bit nonce
5. **AAD Integrity**: Never modify AAD components after encryption
