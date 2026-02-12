"""
EMCL Section-Level Encryption (Phase II)

Provides section-level encryption for execution payloads with:
- AES-256-GCM authenticated encryption
- Per-execution Data Encryption Key (DEK)
- Optional Key Encryption Key (KEK) wrapping
- AAD binding to executionId + canonicalHash + signerId
- Signature verification BEFORE decryption
- Explicit decrypt APIs only (never auto-decrypt)

CRITICAL INVARIANTS:
1. Signature MUST be verified before ANY decryption attempt
2. Decryption is ALWAYS explicit - never auto-decrypt
3. AAD binds ciphertext to execution context
4. Each section can have independent encryption state
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes


# ===========================================================================
# Errors
# ===========================================================================


class EncryptionError(Exception):
    """Base error for encryption operations."""
    pass


class DecryptionError(Exception):
    """Raised when decryption fails."""
    pass


class SignatureNotVerifiedError(Exception):
    """Raised when attempting to decrypt before signature verification."""
    pass


class AADMismatchError(DecryptionError):
    """Raised when AAD does not match during decryption."""
    pass


class KEKNotFoundError(DecryptionError):
    """Raised when required KEK is not available."""
    pass


# ===========================================================================
# Section Types
# ===========================================================================


class SectionType(Enum):
    """Types of sections that can be encrypted."""
    INPUT = "input"
    OUTPUT = "output"
    TRACE = "trace"
    METADATA_CUSTOM = "metadata.custom"


# ===========================================================================
# Key Types
# ===========================================================================


@dataclass(frozen=True)
class ExecutionDEK:
    """
    Data Encryption Key for a single execution.

    Each execution gets a unique DEK derived from entropy.
    The DEK is 256 bits (32 bytes) for AES-256-GCM.

    Attributes:
        execution_id: The execution this DEK belongs to
        key_bytes: The 32-byte DEK (never expose in logs)
        key_id: Identifier for this DEK
        created_at: When this DEK was generated
    """
    execution_id: str
    key_bytes: bytes
    key_id: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self):
        if len(self.key_bytes) != 32:
            raise ValueError("DEK must be exactly 32 bytes (256 bits)")

    @classmethod
    def generate(cls, execution_id: str) -> "ExecutionDEK":
        """Generate a new random DEK for an execution."""
        key_bytes = os.urandom(32)
        key_id = hashlib.sha256(key_bytes).hexdigest()[:16]
        return cls(
            execution_id=execution_id,
            key_bytes=key_bytes,
            key_id=key_id,
        )

    @classmethod
    def derive(cls, execution_id: str, master_secret: bytes, salt: bytes) -> "ExecutionDEK":
        """Derive a DEK deterministically from a master secret."""
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=f"execution-dek:{execution_id}".encode("utf-8"),
        )
        key_bytes = hkdf.derive(master_secret)
        key_id = hashlib.sha256(key_bytes).hexdigest()[:16]
        return cls(
            execution_id=execution_id,
            key_bytes=key_bytes,
            key_id=key_id,
        )


@dataclass(frozen=True)
class KEKWrapper:
    """
    Key Encryption Key wrapper for DEK wrapping.

    KEKs are used to wrap (encrypt) DEKs for secure storage/transport.

    Attributes:
        kek_id: Identifier for this KEK
        wrapped_dek: The DEK encrypted under this KEK
        algorithm: Wrapping algorithm (always AES-256-GCM)
        iv: Nonce used for wrapping
        dek_key_id: Key ID of wrapped DEK (required for AAD reconstruction)
    """
    kek_id: str
    wrapped_dek: str  # Base64-encoded wrapped key
    algorithm: str = "AES-256-GCM"
    iv: str = ""  # Base64-encoded nonce
    dek_key_id: str = ""  # Required for AAD reconstruction during unwrap

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kekId": self.kek_id,
            "wrappedDek": self.wrapped_dek,
            "algorithm": self.algorithm,
            "iv": self.iv,
            "dekKeyId": self.dek_key_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KEKWrapper":
        return cls(
            kek_id=data["kekId"],
            wrapped_dek=data["wrappedDek"],
            algorithm=data.get("algorithm", "AES-256-GCM"),
            iv=data.get("iv", ""),
            dek_key_id=data.get("dekKeyId", ""),
        )


class KEKStore:
    """
    Store for Key Encryption Keys.

    In production, this would be backed by an HSM or KMS.
    """

    def __init__(self):
        self._keks: Dict[str, bytes] = {}

    def add_kek(self, kek_id: str, kek_bytes: bytes) -> None:
        """Add a KEK to the store."""
        if len(kek_bytes) != 32:
            raise ValueError("KEK must be exactly 32 bytes (256 bits)")
        self._keks[kek_id] = kek_bytes

    def get_kek(self, kek_id: str) -> Optional[bytes]:
        """Get a KEK by ID."""
        return self._keks.get(kek_id)

    def has_kek(self, kek_id: str) -> bool:
        """Check if a KEK exists."""
        return kek_id in self._keks

    def wrap_dek(self, dek: ExecutionDEK, kek_id: str) -> KEKWrapper:
        """Wrap a DEK with a KEK."""
        kek_bytes = self._keks.get(kek_id)
        if kek_bytes is None:
            raise KEKNotFoundError(f"KEK '{kek_id}' not found")

        aesgcm = AESGCM(kek_bytes)
        nonce = os.urandom(12)
        aad = f"dek-wrap:{dek.execution_id}:{dek.key_id}".encode("utf-8")

        wrapped = aesgcm.encrypt(nonce, dek.key_bytes, aad)

        return KEKWrapper(
            kek_id=kek_id,
            wrapped_dek=base64.b64encode(wrapped).decode("ascii"),
            algorithm="AES-256-GCM",
            iv=base64.b64encode(nonce).decode("ascii"),
            dek_key_id=dek.key_id,
        )

    def unwrap_dek(self, wrapper: KEKWrapper, execution_id: str) -> ExecutionDEK:
        """Unwrap a DEK from its KEK wrapper."""
        kek_bytes = self._keks.get(wrapper.kek_id)
        if kek_bytes is None:
            raise KEKNotFoundError(f"KEK '{wrapper.kek_id}' not found")

        if not wrapper.dek_key_id:
            raise DecryptionError("KEKWrapper missing dek_key_id for AAD reconstruction")

        aesgcm = AESGCM(kek_bytes)
        nonce = base64.b64decode(wrapper.iv)
        wrapped = base64.b64decode(wrapper.wrapped_dek)

        # Reconstruct AAD using stored dek_key_id
        aad = f"dek-wrap:{execution_id}:{wrapper.dek_key_id}".encode("utf-8")

        try:
            dek_bytes = aesgcm.decrypt(nonce, wrapped, aad)
        except Exception:
            raise DecryptionError("Failed to unwrap DEK: AAD mismatch or corrupted data")

        return ExecutionDEK(
            execution_id=execution_id,
            key_bytes=dek_bytes,
            key_id=wrapper.dek_key_id,
        )


# ===========================================================================
# Encrypted Section
# ===========================================================================


@dataclass
class EncryptedSection:
    """
    An encrypted section of an execution payload.

    Attributes:
        section_type: Which section this encrypts
        ciphertext: Base64-encoded encrypted data
        iv: Base64-encoded nonce (12 bytes for GCM)
        aad_components: Components used to construct AAD
        dek_id: ID of the DEK used for encryption
        kek_wrapper: Optional KEK-wrapped DEK
    """
    section_type: str
    ciphertext: str
    iv: str
    aad_components: Dict[str, str]
    dek_id: str
    kek_wrapper: Optional[KEKWrapper] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "sectionType": self.section_type,
            "ciphertext": self.ciphertext,
            "iv": self.iv,
            "aadComponents": self.aad_components,
            "dekId": self.dek_id,
        }
        if self.kek_wrapper:
            result["kekWrapper"] = self.kek_wrapper.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EncryptedSection":
        kek_data = data.get("kekWrapper")
        kek_wrapper = KEKWrapper.from_dict(kek_data) if kek_data else None

        return cls(
            section_type=data["sectionType"],
            ciphertext=data["ciphertext"],
            iv=data["iv"],
            aad_components=data["aadComponents"],
            dek_id=data["dekId"],
            kek_wrapper=kek_wrapper,
        )


# ===========================================================================
# Encrypted Execution Payload
# ===========================================================================


@dataclass
class EncryptedExecutionPayload:
    """
    Container for all encrypted sections of an execution.

    Attributes:
        execution_id: The execution these sections belong to
        sections: Map of section type to encrypted section
        canonical_hash: Hash of the execution for AAD binding
        signer_id: Gateway signer ID for AAD binding
        signature_verified: Whether the execution signature was verified
    """
    execution_id: str
    sections: Dict[str, EncryptedSection]
    canonical_hash: str
    signer_id: str
    signature_verified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "executionId": self.execution_id,
            "sections": {k: v.to_dict() for k, v in self.sections.items()},
            "canonicalHash": self.canonical_hash,
            "signerId": self.signer_id,
            "signatureVerified": self.signature_verified,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EncryptedExecutionPayload":
        sections = {
            k: EncryptedSection.from_dict(v)
            for k, v in data.get("sections", {}).items()
        }
        return cls(
            execution_id=data["executionId"],
            sections=sections,
            canonical_hash=data["canonicalHash"],
            signer_id=data["signerId"],
            signature_verified=data.get("signatureVerified", False),
        )

    def get_section(self, section_type: SectionType) -> Optional[EncryptedSection]:
        """Get an encrypted section by type."""
        return self.sections.get(section_type.value)

    def has_section(self, section_type: SectionType) -> bool:
        """Check if a section is encrypted."""
        return section_type.value in self.sections


# ===========================================================================
# Encryption Configuration
# ===========================================================================


@dataclass
class SectionEncryptionConfig:
    """
    Configuration for which sections to encrypt.

    Attributes:
        encrypt_input: Whether to encrypt input section
        encrypt_output: Whether to encrypt output section
        encrypt_trace: Whether to encrypt trace section
        encrypt_metadata_custom: Whether to encrypt metadata.custom
        use_kek_wrapping: Whether to wrap DEKs with KEK
        kek_id: KEK ID for wrapping (if use_kek_wrapping)
    """
    encrypt_input: bool = True
    encrypt_output: bool = True
    encrypt_trace: bool = True
    encrypt_metadata_custom: bool = False
    use_kek_wrapping: bool = False
    kek_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "encryptInput": self.encrypt_input,
            "encryptOutput": self.encrypt_output,
            "encryptTrace": self.encrypt_trace,
            "encryptMetadataCustom": self.encrypt_metadata_custom,
            "useKekWrapping": self.use_kek_wrapping,
            "kekId": self.kek_id,
        }


# ===========================================================================
# Decryption Request / Result
# ===========================================================================


@dataclass
class DecryptionRequest:
    """
    Request to decrypt a section.

    CRITICAL: Signature must be verified before this request is processed.

    Attributes:
        execution_id: The execution to decrypt
        section_type: Which section to decrypt
        signature_verified: Whether signature was verified (REQUIRED)
        dek: The DEK to use (or will be unwrapped from KEK)
    """
    execution_id: str
    section_type: SectionType
    signature_verified: bool
    dek: Optional[ExecutionDEK] = None

    def validate(self) -> None:
        """Validate the decryption request."""
        if not self.signature_verified:
            raise SignatureNotVerifiedError(
                "Signature MUST be verified before decryption. "
                "Set signature_verified=True only after verification."
            )


@dataclass
class DecryptionResult:
    """
    Result of a decryption operation.

    Attributes:
        execution_id: The execution that was decrypted
        section_type: Which section was decrypted
        plaintext: The decrypted data
        success: Whether decryption succeeded
        error: Error message if decryption failed
    """
    execution_id: str
    section_type: SectionType
    plaintext: Optional[Dict[str, Any]]
    success: bool
    error: Optional[str] = None


# ===========================================================================
# Section Encryptor
# ===========================================================================


def _json_dumps(obj: Any) -> str:
    """Canonical JSON serialization."""
    return json.dumps(obj, separators=(",", ":"), sort_keys=True, ensure_ascii=True)


def _json_loads(s: str) -> Any:
    """Parse JSON."""
    return json.loads(s)


def _compute_aad(
    execution_id: str,
    canonical_hash: str,
    signer_id: str,
    section_type: str,
) -> bytes:
    """
    Compute AAD for a section.

    AAD binds the ciphertext to the execution context:
    - executionId: Unique execution identifier
    - canonicalHash: Hash of the execution content
    - signerId: Gateway that signed the execution
    - sectionType: Which section is being encrypted

    This prevents:
    - Moving ciphertext between executions
    - Substituting sections
    - Replay attacks
    """
    aad_struct = {
        "executionId": execution_id,
        "canonicalHash": canonical_hash,
        "signerId": signer_id,
        "sectionType": section_type,
    }
    return _json_dumps(aad_struct).encode("utf-8")


class SectionEncryptor:
    """
    Section-level encryptor for execution payloads.

    Provides AES-256-GCM encryption with AAD binding.
    """

    def __init__(self, kek_store: Optional[KEKStore] = None):
        self._kek_store = kek_store or KEKStore()

    def encrypt_section(
        self,
        section_type: SectionType,
        plaintext: Any,
        execution_id: str,
        canonical_hash: str,
        signer_id: str,
        dek: ExecutionDEK,
        kek_id: Optional[str] = None,
    ) -> EncryptedSection:
        """
        Encrypt a section with AAD binding.

        Args:
            section_type: Which section to encrypt
            plaintext: Data to encrypt (will be JSON serialized)
            execution_id: Execution ID for AAD
            canonical_hash: Canonical hash for AAD
            signer_id: Signer ID for AAD
            dek: Data encryption key
            kek_id: Optional KEK ID for key wrapping

        Returns:
            EncryptedSection with ciphertext and metadata
        """
        # Serialize plaintext
        plaintext_bytes = _json_dumps(plaintext).encode("utf-8")

        # Compute AAD
        aad = _compute_aad(execution_id, canonical_hash, signer_id, section_type.value)

        # Encrypt
        aesgcm = AESGCM(dek.key_bytes)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, aad)

        # Optional KEK wrapping
        kek_wrapper = None
        if kek_id and self._kek_store.has_kek(kek_id):
            kek_wrapper = self._kek_store.wrap_dek(dek, kek_id)

        return EncryptedSection(
            section_type=section_type.value,
            ciphertext=base64.b64encode(ciphertext).decode("ascii"),
            iv=base64.b64encode(nonce).decode("ascii"),
            aad_components={
                "executionId": execution_id,
                "canonicalHash": canonical_hash,
                "signerId": signer_id,
                "sectionType": section_type.value,
            },
            dek_id=dek.key_id,
            kek_wrapper=kek_wrapper,
        )

    def decrypt_section(
        self,
        section: EncryptedSection,
        request: DecryptionRequest,
    ) -> DecryptionResult:
        """
        Decrypt a section.

        CRITICAL: Signature MUST be verified before calling this method.

        Args:
            section: The encrypted section
            request: Decryption request with verified signature flag

        Returns:
            DecryptionResult with plaintext or error
        """
        # CRITICAL: Validate signature was verified
        try:
            request.validate()
        except SignatureNotVerifiedError as e:
            return DecryptionResult(
                execution_id=request.execution_id,
                section_type=request.section_type,
                plaintext=None,
                success=False,
                error=str(e),
            )

        try:
            # Get DEK
            dek = request.dek
            if dek is None:
                if section.kek_wrapper:
                    dek = self._kek_store.unwrap_dek(
                        section.kek_wrapper,
                        request.execution_id,
                    )
                else:
                    return DecryptionResult(
                        execution_id=request.execution_id,
                        section_type=request.section_type,
                        plaintext=None,
                        success=False,
                        error="DEK not provided and no KEK wrapper available",
                    )

            # Decode ciphertext and nonce
            ciphertext = base64.b64decode(section.ciphertext)
            nonce = base64.b64decode(section.iv)

            # Reconstruct AAD from stored components
            aad = _compute_aad(
                section.aad_components["executionId"],
                section.aad_components["canonicalHash"],
                section.aad_components["signerId"],
                section.aad_components["sectionType"],
            )

            # Verify AAD matches request context
            expected_aad = _compute_aad(
                request.execution_id,
                section.aad_components["canonicalHash"],
                section.aad_components["signerId"],
                request.section_type.value,
            )

            if aad != expected_aad:
                raise AADMismatchError(
                    "AAD mismatch: section was encrypted for different context"
                )

            # Decrypt
            aesgcm = AESGCM(dek.key_bytes)
            plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, aad)

            # Parse JSON
            plaintext = _json_loads(plaintext_bytes.decode("utf-8"))

            return DecryptionResult(
                execution_id=request.execution_id,
                section_type=request.section_type,
                plaintext=plaintext,
                success=True,
            )

        except AADMismatchError as e:
            return DecryptionResult(
                execution_id=request.execution_id,
                section_type=request.section_type,
                plaintext=None,
                success=False,
                error=str(e),
            )
        except Exception as e:
            return DecryptionResult(
                execution_id=request.execution_id,
                section_type=request.section_type,
                plaintext=None,
                success=False,
                error=f"Decryption failed: {e}",
            )

    def encrypt_execution(
        self,
        execution_id: str,
        canonical_hash: str,
        signer_id: str,
        input_payload: Optional[Dict[str, Any]],
        output_payload: Optional[Dict[str, Any]],
        trace: Optional[List[Dict[str, Any]]],
        metadata_custom: Optional[Dict[str, Any]],
        config: SectionEncryptionConfig,
    ) -> Tuple[EncryptedExecutionPayload, ExecutionDEK]:
        """
        Encrypt all configured sections of an execution.

        Args:
            execution_id: Unique execution identifier
            canonical_hash: Hash of the execution
            signer_id: Gateway signer ID
            input_payload: Input to encrypt (if configured)
            output_payload: Output to encrypt (if configured)
            trace: Trace to encrypt (if configured)
            metadata_custom: Custom metadata to encrypt (if configured)
            config: Encryption configuration

        Returns:
            Tuple of (EncryptedExecutionPayload, DEK used for encryption)
        """
        # Generate DEK for this execution
        dek = ExecutionDEK.generate(execution_id)

        sections: Dict[str, EncryptedSection] = {}

        # Encrypt input
        if config.encrypt_input and input_payload is not None:
            sections[SectionType.INPUT.value] = self.encrypt_section(
                SectionType.INPUT,
                input_payload,
                execution_id,
                canonical_hash,
                signer_id,
                dek,
                config.kek_id if config.use_kek_wrapping else None,
            )

        # Encrypt output
        if config.encrypt_output and output_payload is not None:
            sections[SectionType.OUTPUT.value] = self.encrypt_section(
                SectionType.OUTPUT,
                output_payload,
                execution_id,
                canonical_hash,
                signer_id,
                dek,
                config.kek_id if config.use_kek_wrapping else None,
            )

        # Encrypt trace
        if config.encrypt_trace and trace is not None:
            sections[SectionType.TRACE.value] = self.encrypt_section(
                SectionType.TRACE,
                trace,
                execution_id,
                canonical_hash,
                signer_id,
                dek,
                config.kek_id if config.use_kek_wrapping else None,
            )

        # Encrypt metadata.custom
        if config.encrypt_metadata_custom and metadata_custom is not None:
            sections[SectionType.METADATA_CUSTOM.value] = self.encrypt_section(
                SectionType.METADATA_CUSTOM,
                metadata_custom,
                execution_id,
                canonical_hash,
                signer_id,
                dek,
                config.kek_id if config.use_kek_wrapping else None,
            )

        payload = EncryptedExecutionPayload(
            execution_id=execution_id,
            sections=sections,
            canonical_hash=canonical_hash,
            signer_id=signer_id,
            signature_verified=False,  # Caller must verify and set
        )

        return payload, dek
