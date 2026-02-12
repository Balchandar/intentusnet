"""
IntentusNet v1.4.1 Deterministic Agent - Tool Registry

This module defines the tool registry with strict classification for
deterministic execution. All tools must be:
- Classified by side-effect (read_only, state_changing, external)
- Typed with strict type hints
- Deterministic parameter hashing
- Serializable outputs
- Idempotency key required for state-changing tools

CRITICAL: External tools MUST use MCP adapters (intentusnet.mcp).
Direct HTTP/SDK/network calls are FORBIDDEN as they break deterministic
replay guarantees.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, TypeVar, Generic
from enum import Enum

from .models import (
    SideEffectClass,
    WALEntry,
    LatencyMetadata,
    RetryReason,
    compute_params_hash,
    compute_output_hash,
    current_time_ms,
)

T = TypeVar("T")


class ToolExecutionError(Exception):
    """Exception raised when tool execution fails."""
    def __init__(
        self,
        message: str,
        retry_reason: RetryReason = RetryReason.RUNTIME_ERROR,
        recoverable: bool = False,
    ):
        super().__init__(message)
        self.retry_reason = retry_reason
        self.recoverable = recoverable


@dataclass
class ToolSchema:
    """
    IntentusNet v1.4.1 Tool Schema Definition.

    Defines the contract for a deterministic tool including:
    - Name and description
    - Side-effect classification
    - Input/output type hints
    - Timeout configuration
    - Idempotency requirements
    """
    name: str
    description: str
    side_effect_class: SideEffectClass
    timeout_ms: int = 30000  # Default 30 second timeout
    max_retries: int = 0  # Default no retries for state-changing
    requires_mcp: bool = False  # External tools must use MCP

    # Type hints for validation
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Validate schema constraints
        if self.side_effect_class == SideEffectClass.EXTERNAL and not self.requires_mcp:
            raise ValueError(
                f"Tool '{self.name}' is classified as EXTERNAL but requires_mcp=False. "
                "External tools MUST use MCP adapters for deterministic replay."
            )

        if self.side_effect_class == SideEffectClass.STATE_CHANGING and self.max_retries > 0:
            raise ValueError(
                f"Tool '{self.name}' is STATE_CHANGING with max_retries > 0. "
                "State-changing tools must NOT retry to prevent duplicate side-effects."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "side_effect_class": self.side_effect_class.value,
            "timeout_ms": self.timeout_ms,
            "max_retries": self.max_retries,
            "requires_mcp": self.requires_mcp,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }


class BaseTool(ABC):
    """
    Abstract base class for deterministic tools.

    All tools must inherit from this class and implement:
    - schema: Tool schema definition
    - execute: Deterministic execution logic

    The base class provides:
    - Parameter hashing
    - Output hashing
    - Latency tracking
    - WAL entry generation
    """

    @property
    @abstractmethod
    def schema(self) -> ToolSchema:
        """Return the tool schema definition."""
        ...

    @abstractmethod
    def execute(self, params: dict[str, Any]) -> Any:
        """
        Execute the tool with given parameters.

        Args:
            params: Tool input parameters (must match input_schema)

        Returns:
            Tool output (must match output_schema and be JSON-serializable)

        Raises:
            ToolExecutionError: If execution fails
        """
        ...

    def validate_params(self, params: dict[str, Any]) -> bool:
        """Validate parameters against input schema."""
        # Basic validation - in production, use jsonschema
        required_keys = self.schema.input_schema.get("required", [])
        for key in required_keys:
            if key not in params:
                raise ToolExecutionError(
                    f"Missing required parameter: {key}",
                    retry_reason=RetryReason.MALFORMED_OUTPUT,
                    recoverable=False,
                )
        return True

    def validate_output(self, output: Any) -> bool:
        """Validate output is JSON-serializable."""
        try:
            json.dumps(output, default=str)
            return True
        except (TypeError, ValueError) as e:
            raise ToolExecutionError(
                f"Output is not JSON-serializable: {e}",
                retry_reason=RetryReason.MALFORMED_OUTPUT,
                recoverable=False,
            )

    def create_wal_entry(
        self,
        execution_id: str,
        intent: str,
        execution_order: int,
        params: dict[str, Any],
        output: Any,
        latency: LatencyMetadata,
        retry_count: int = 0,
        retry_reason: RetryReason = RetryReason.NONE,
        prev_hash: Optional[str] = None,
    ) -> WALEntry:
        """
        Create a WAL entry for this tool execution.

        This generates a complete audit record for deterministic replay.
        """
        entry = WALEntry(
            execution_id=execution_id,
            intent=intent,
            tool_name=self.schema.name,
            execution_order=execution_order,
            params_hash=compute_params_hash(params),
            params_snapshot=params,
            output_hash=compute_output_hash(output),
            output_snapshot=output,
            side_effect_class=self.schema.side_effect_class,
            retry_count=retry_count,
            retry_reason=retry_reason,
            latency_metadata=latency,
            prev_hash=prev_hash,
        )

        # Generate idempotency key
        entry.idempotency_key = entry.generate_idempotency_key()

        # Compute entry hash
        entry.entry_hash = entry.compute_hash()

        return entry


# =============================================================================
# EXAMPLE TOOL IMPLEMENTATIONS
# =============================================================================


class FetchContextTool(BaseTool):
    """
    Read-only tool for fetching context data.

    Classification: READ_ONLY (no side-effects, safe to retry/replay)
    """

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="fetch_context",
            description="Fetch context data from local storage or cache",
            side_effect_class=SideEffectClass.READ_ONLY,
            timeout_ms=5000,
            max_retries=3,  # Safe to retry read-only operations
            requires_mcp=False,
            input_schema={
                "type": "object",
                "properties": {
                    "context_key": {"type": "string"},
                    "include_metadata": {"type": "boolean", "default": False},
                },
                "required": ["context_key"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "data": {"type": "object"},
                    "metadata": {"type": "object"},
                },
            },
        )

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Fetch context data."""
        self.validate_params(params)

        context_key = params["context_key"]
        include_metadata = params.get("include_metadata", False)

        # Simulated context fetch - in production, this would read from storage
        result = {
            "data": {
                "key": context_key,
                "value": f"context_value_for_{context_key}",
                "timestamp": "2026-02-09T10:00:00Z",
            },
        }

        if include_metadata:
            result["metadata"] = {
                "source": "local_cache",
                "ttl_seconds": 3600,
            }

        self.validate_output(result)
        return result


class UpdateDatabaseTool(BaseTool):
    """
    State-changing tool for database updates.

    Classification: STATE_CHANGING (requires idempotency key, NO retries)

    CRITICAL: This tool modifies state. The idempotency key MUST be
    checked before execution to prevent duplicate side-effects.
    """

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="update_database",
            description="Update a record in the database (state-changing operation)",
            side_effect_class=SideEffectClass.STATE_CHANGING,
            timeout_ms=10000,
            max_retries=0,  # NEVER retry state-changing operations
            requires_mcp=False,
            input_schema={
                "type": "object",
                "properties": {
                    "table": {"type": "string"},
                    "record_id": {"type": "string"},
                    "data": {"type": "object"},
                },
                "required": ["table", "record_id", "data"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "affected_rows": {"type": "integer"},
                    "transaction_id": {"type": "string"},
                },
            },
        )

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute database update."""
        self.validate_params(params)

        table = params["table"]
        record_id = params["record_id"]
        data = params["data"]

        # Simulated database update - in production, this would update actual DB
        # The transaction_id is deterministic based on input for replay verification
        transaction_id = hashlib.sha256(
            f"{table}:{record_id}:{json.dumps(data, sort_keys=True)}".encode()
        ).hexdigest()[:16]

        result = {
            "success": True,
            "affected_rows": 1,
            "transaction_id": transaction_id,
        }

        self.validate_output(result)
        return result


class ExternalAPICallTool(BaseTool):
    """
    External tool for API calls via MCP adapter.

    Classification: EXTERNAL (high latency, MCP REQUIRED)

    CRITICAL: This tool MUST use MCP adapters for all network calls.
    Direct HTTP/SDK calls are FORBIDDEN as they break deterministic
    replay guarantees.

    MCP adapters provide:
    - Normalized timeouts
    - Captured latency metadata
    - Enforced retry determinism
    - Serializable outputs
    - Replay-safe execution
    """

    def __init__(self, mcp_adapter: Any = None):
        """
        Initialize with MCP adapter.

        Args:
            mcp_adapter: IntentusNet MCP adapter for external calls
        """
        self._mcp_adapter = mcp_adapter

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="external_api_call",
            description="Make external API call via MCP adapter (replay-safe)",
            side_effect_class=SideEffectClass.EXTERNAL,
            timeout_ms=30000,  # Higher timeout for external calls
            max_retries=2,  # Limited retries via MCP
            requires_mcp=True,  # MANDATORY for external tools
            input_schema={
                "type": "object",
                "properties": {
                    "endpoint": {"type": "string"},
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]},
                    "payload": {"type": "object"},
                    "headers": {"type": "object"},
                },
                "required": ["endpoint", "method"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "status_code": {"type": "integer"},
                    "response": {"type": "object"},
                    "latency_ms": {"type": "integer"},
                },
            },
        )

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Execute external API call via MCP adapter.

        CRITICAL: All network calls MUST go through MCP adapter.
        """
        self.validate_params(params)

        if self._mcp_adapter is None:
            raise ToolExecutionError(
                "External API calls require MCP adapter. "
                "Direct network calls are FORBIDDEN for deterministic replay.",
                retry_reason=RetryReason.RUNTIME_ERROR,
                recoverable=False,
            )

        # Execute via MCP adapter
        response = self._mcp_adapter.call(
            endpoint=params["endpoint"],
            method=params["method"],
            payload=params.get("payload", {}),
            headers=params.get("headers", {}),
            timeout_ms=self.schema.timeout_ms,
        )

        self.validate_output(response)
        return response


# =============================================================================
# TOOL REGISTRY
# =============================================================================


class ToolRegistry:
    """
    Registry for deterministic tools.

    Provides:
    - Tool registration with validation
    - Tool lookup by name
    - Tool classification queries
    - Schema export for documentation
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._executed_idempotency_keys: set[str] = set()

    def register(self, tool: BaseTool) -> None:
        """
        Register a tool in the registry.

        Validates the tool schema before registration.
        """
        if tool.schema.name in self._tools:
            raise ValueError(f"Tool '{tool.schema.name}' is already registered")
        self._tools[tool.schema.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_required(self, name: str) -> BaseTool:
        """Get a tool by name, raising if not found."""
        tool = self.get(name)
        if tool is None:
            raise KeyError(f"Tool '{name}' not found in registry")
        return tool

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def list_by_classification(
        self, side_effect_class: SideEffectClass
    ) -> list[str]:
        """List tools by side-effect classification."""
        return [
            name for name, tool in self._tools.items()
            if tool.schema.side_effect_class == side_effect_class
        ]

    def check_idempotency(self, idempotency_key: str) -> bool:
        """
        Check if an idempotency key has been executed.

        Returns True if the key has already been used (execution should be skipped).
        """
        return idempotency_key in self._executed_idempotency_keys

    def mark_executed(self, idempotency_key: str) -> None:
        """Mark an idempotency key as executed."""
        self._executed_idempotency_keys.add(idempotency_key)

    def export_schemas(self) -> list[dict[str, Any]]:
        """Export all tool schemas for documentation."""
        return [tool.schema.to_dict() for tool in self._tools.values()]

    def clear_idempotency_cache(self) -> None:
        """Clear the idempotency cache (for testing only)."""
        self._executed_idempotency_keys.clear()


def create_default_registry(mcp_adapter: Any = None) -> ToolRegistry:
    """
    Create a tool registry with default tools.

    Args:
        mcp_adapter: Optional MCP adapter for external tools

    Returns:
        Configured ToolRegistry with standard tools
    """
    registry = ToolRegistry()

    # Register read-only tools
    registry.register(FetchContextTool())

    # Register state-changing tools
    registry.register(UpdateDatabaseTool())

    # Register external tools (requires MCP adapter)
    registry.register(ExternalAPICallTool(mcp_adapter=mcp_adapter))

    return registry
