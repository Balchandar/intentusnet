"""
Proof Export (Time Machine UI - Phase II)

Provides export of proof bundles for offline verification.

UI REQUIREMENTS:
- Export execution proof bundle
- Include:
  - Execution canonical hash
  - Signatures
  - Witness attestations
  - Batch inclusion proof
  - Transparency log inclusion proof
- Export must be offline-verifiable
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from intentusnet.phase2.timemachine.api.core import (
    TimeMachineAPI,
    ProofExportBundle,
)


# ===========================================================================
# Export Format
# ===========================================================================


class ExportFormat(Enum):
    """Supported export formats."""
    JSON = "json"
    JSON_COMPACT = "json_compact"
    BASE64 = "base64"


# ===========================================================================
# Export Options
# ===========================================================================


@dataclass
class ExportOptions:
    """
    Options for proof export.

    Attributes:
        format: Export format
        include_witness_attestations: Include witness attestations
        include_batch_proof: Include batch inclusion proof
        include_log_proof: Include log inclusion proof
        include_checkpoint: Include transparency checkpoint
        pretty_print: Pretty print JSON (for JSON format)
    """
    format: ExportFormat = ExportFormat.JSON
    include_witness_attestations: bool = True
    include_batch_proof: bool = True
    include_log_proof: bool = True
    include_checkpoint: bool = True
    pretty_print: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "format": self.format.value,
            "includeWitnessAttestations": self.include_witness_attestations,
            "includeBatchProof": self.include_batch_proof,
            "includeLogProof": self.include_log_proof,
            "includeCheckpoint": self.include_checkpoint,
            "prettyPrint": self.pretty_print,
        }


# ===========================================================================
# Export Result
# ===========================================================================


@dataclass
class ExportResult:
    """
    Result of proof export.

    Attributes:
        success: Whether export succeeded
        execution_id: Execution that was exported
        bundle_hash: Hash of the exported bundle
        format: Format of the export
        data: Exported data (format depends on format option)
        filename_suggestion: Suggested filename
        error: Error message if export failed
    """
    success: bool
    execution_id: str
    bundle_hash: Optional[str] = None
    format: ExportFormat = ExportFormat.JSON
    data: Optional[str] = None
    filename_suggestion: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "executionId": self.execution_id,
            "bundleHash": self.bundle_hash,
            "format": self.format.value,
            "data": self.data,
            "filenameSuggestion": self.filename_suggestion,
            "error": self.error,
        }


# ===========================================================================
# Proof Exporter
# ===========================================================================


class ProofExporter:
    """
    Proof exporter for the Time Machine UI.

    Exports proof bundles that can be verified offline.

    The export includes:
    - Execution canonical hash
    - Gateway signatures
    - Witness attestations
    - Batch inclusion proof
    - Transparency log inclusion proof
    - Verification metadata
    """

    def __init__(self, api: TimeMachineAPI):
        """
        Initialize the proof exporter.

        Args:
            api: Time Machine API instance
        """
        self._api = api

    def export(
        self,
        execution_id: str,
        options: Optional[ExportOptions] = None,
    ) -> ExportResult:
        """
        Export proof bundle for an execution.

        Args:
            execution_id: Execution to export
            options: Export options

        Returns:
            ExportResult with exported data
        """
        options = options or ExportOptions()

        try:
            # Get proof bundle from API
            bundle = self._api.export_proof_bundle(execution_id)

            if bundle is None:
                return ExportResult(
                    success=False,
                    execution_id=execution_id,
                    error="Execution not found",
                )

            # Filter based on options
            filtered_bundle = self._filter_bundle(bundle, options)

            # Format the export
            data = self._format_export(filtered_bundle, options)

            # Generate filename
            filename = self._generate_filename(execution_id, options.format)

            return ExportResult(
                success=True,
                execution_id=execution_id,
                bundle_hash=filtered_bundle.bundle_hash,
                format=options.format,
                data=data,
                filename_suggestion=filename,
            )

        except Exception as e:
            return ExportResult(
                success=False,
                execution_id=execution_id,
                error=str(e),
            )

    def _filter_bundle(
        self,
        bundle: ProofExportBundle,
        options: ExportOptions,
    ) -> ProofExportBundle:
        """Filter bundle based on export options."""
        filtered = ProofExportBundle(
            execution_id=bundle.execution_id,
            canonical_hash=bundle.canonical_hash,
            gateway_signature=bundle.gateway_signature,
            exported_at=bundle.exported_at,
        )

        if options.include_witness_attestations:
            filtered.witness_attestations = bundle.witness_attestations

        if options.include_batch_proof:
            filtered.batch_inclusion_proof = bundle.batch_inclusion_proof

        if options.include_log_proof:
            filtered.log_inclusion_proof = bundle.log_inclusion_proof

        if options.include_checkpoint:
            filtered.checkpoint = bundle.checkpoint

        # Recompute bundle hash
        filtered.bundle_hash = filtered.compute_bundle_hash()

        return filtered

    def _format_export(
        self,
        bundle: ProofExportBundle,
        options: ExportOptions,
    ) -> str:
        """Format bundle for export."""
        bundle_dict = bundle.to_dict()

        # Add verification metadata
        bundle_dict["_verification"] = {
            "version": "2.0",
            "algorithm": "Ed25519",
            "hashAlgorithm": "SHA-256",
            "bundleHash": bundle.bundle_hash,
            "exportedAt": bundle.exported_at,
        }

        if options.format == ExportFormat.JSON:
            if options.pretty_print:
                return json.dumps(bundle_dict, indent=2, sort_keys=True)
            else:
                return json.dumps(bundle_dict, separators=(",", ":"), sort_keys=True)

        elif options.format == ExportFormat.JSON_COMPACT:
            return json.dumps(bundle_dict, separators=(",", ":"), sort_keys=True)

        elif options.format == ExportFormat.BASE64:
            json_str = json.dumps(bundle_dict, separators=(",", ":"), sort_keys=True)
            return base64.b64encode(json_str.encode("utf-8")).decode("ascii")

        else:
            return json.dumps(bundle_dict, indent=2, sort_keys=True)

    def _generate_filename(
        self,
        execution_id: str,
        format: ExportFormat,
    ) -> str:
        """Generate suggested filename for export."""
        short_id = execution_id[:8]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

        if format == ExportFormat.BASE64:
            return f"proof-{short_id}-{timestamp}.b64"
        else:
            return f"proof-{short_id}-{timestamp}.json"

    def verify_export(self, data: str, format: ExportFormat) -> Dict[str, Any]:
        """
        Verify an exported proof bundle.

        This can be used to verify an export without any external dependencies.

        Args:
            data: Exported data
            format: Format of the data

        Returns:
            Dict with verification results
        """
        try:
            # Parse the export
            if format == ExportFormat.BASE64:
                json_str = base64.b64decode(data).decode("utf-8")
                bundle_dict = json.loads(json_str)
            else:
                bundle_dict = json.loads(data)

            # Get stored bundle hash
            stored_hash = bundle_dict.get("bundleHash")
            verification_meta = bundle_dict.get("_verification", {})

            # Remove verification metadata for hash computation
            bundle_copy = {k: v for k, v in bundle_dict.items() if k != "_verification"}

            # Recompute bundle hash
            content = {
                "executionId": bundle_copy.get("executionId"),
                "canonicalHash": bundle_copy.get("canonicalHash"),
                "gatewaySignature": bundle_copy.get("gatewaySignature"),
                "witnessAttestations": bundle_copy.get("witnessAttestations", []),
                "batchInclusionProof": bundle_copy.get("batchInclusionProof"),
                "logInclusionProof": bundle_copy.get("logInclusionProof"),
                "checkpoint": bundle_copy.get("checkpoint"),
            }
            canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
            computed_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

            # Check hash match
            hash_valid = computed_hash == stored_hash

            return {
                "valid": hash_valid,
                "executionId": bundle_dict.get("executionId"),
                "canonicalHash": bundle_dict.get("canonicalHash"),
                "storedBundleHash": stored_hash,
                "computedBundleHash": computed_hash,
                "hashMatch": hash_valid,
                "hasGatewaySignature": bundle_dict.get("gatewaySignature") is not None,
                "witnessCount": len(bundle_dict.get("witnessAttestations", [])),
                "hasBatchProof": bundle_dict.get("batchInclusionProof") is not None,
                "hasLogProof": bundle_dict.get("logInclusionProof") is not None,
                "exportedAt": bundle_dict.get("exportedAt"),
            }

        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
            }

    def get_export_summary(
        self,
        execution_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get summary of what would be exported.

        Args:
            execution_id: Execution ID

        Returns:
            Summary dict or None if execution not found
        """
        bundle = self._api.export_proof_bundle(execution_id)

        if bundle is None:
            return None

        return {
            "executionId": bundle.execution_id,
            "canonicalHash": bundle.canonical_hash,
            "hasGatewaySignature": bundle.gateway_signature is not None,
            "witnessCount": len(bundle.witness_attestations),
            "hasBatchProof": bundle.batch_inclusion_proof is not None,
            "hasLogProof": bundle.log_inclusion_proof is not None,
            "hasCheckpoint": bundle.checkpoint is not None,
            "bundleHash": bundle.bundle_hash,
        }
