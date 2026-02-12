"""
IntentusNet v1.4.1 Deterministic Agent - MCP Adapter

Model Context Protocol (MCP) adapter for deterministic external service calls.

This adapter is MANDATORY for all external tool connectivity because it:
- Normalizes timeouts across all external calls
- Captures latency metadata for fingerprint computation
- Enforces retry determinism (same retry pattern on replay)
- Produces serializable outputs (no network objects)
- Is replay-safe (can mock responses for replay verification)

CRITICAL: Direct HTTP/SDK/network calls are FORBIDDEN in deterministic agents.
All external calls MUST go through this MCP adapter.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from enum import Enum

from .models import (
    LatencyMetadata,
    RetryReason,
    current_time_ms,
)


class MCPError(Exception):
    """Exception raised by MCP adapter."""
    def __init__(
        self,
        message: str,
        status_code: int = 0,
        retry_reason: RetryReason = RetryReason.NETWORK_ERROR,
        recoverable: bool = True,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.retry_reason = retry_reason
        self.recoverable = recoverable


@dataclass
class MCPRequest:
    """
    MCP request wrapper for deterministic external calls.

    All fields are captured for replay verification.
    """
    endpoint: str
    method: str
    payload: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 30000

    def compute_hash(self) -> str:
        """Compute deterministic hash of request for idempotency."""
        data = {
            "endpoint": self.endpoint,
            "method": self.method,
            "payload": self.payload,
            "headers": {k: v for k, v in self.headers.items() if k.lower() != "authorization"},
        }
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "method": self.method,
            "payload": self.payload,
            "headers": self.headers,
            "timeout_ms": self.timeout_ms,
        }


@dataclass
class MCPResponse:
    """
    MCP response wrapper with latency metadata.

    All responses are serializable for WAL storage.
    """
    status_code: int
    response: dict[str, Any]
    latency_metadata: LatencyMetadata
    request_hash: str = ""
    success: bool = True
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status_code": self.status_code,
            "response": self.response,
            "latency_ms": self.latency_metadata.duration_ms,
            "success": self.success,
            "error_message": self.error_message,
        }


class RetryPolicy:
    """
    Deterministic retry policy for MCP calls.

    The retry pattern is recorded in WAL and must be reproducible
    on replay for fingerprint verification.
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay_ms: int = 1000,
        max_delay_ms: int = 10000,
        exponential_backoff: bool = True,
    ):
        self.max_retries = max_retries
        self.base_delay_ms = base_delay_ms
        self.max_delay_ms = max_delay_ms
        self.exponential_backoff = exponential_backoff

    def get_delay(self, retry_count: int) -> int:
        """
        Compute delay for given retry count.

        Returns deterministic delay in milliseconds.
        """
        if not self.exponential_backoff:
            return self.base_delay_ms

        delay = self.base_delay_ms * (2 ** retry_count)
        return min(delay, self.max_delay_ms)

    def should_retry(self, retry_count: int, error: MCPError) -> bool:
        """Determine if retry should be attempted."""
        if retry_count >= self.max_retries:
            return False

        # Don't retry non-recoverable errors
        if not error.recoverable:
            return False

        # Retry on specific error types
        retryable_reasons = {
            RetryReason.TIMEOUT,
            RetryReason.NETWORK_ERROR,
            RetryReason.RATE_LIMITED,
        }

        return error.retry_reason in retryable_reasons


class MCPAdapter:
    """
    Deterministic MCP adapter for external service calls.

    This adapter provides:
    - Normalized timeout handling
    - Latency metadata capture
    - Deterministic retry behavior
    - Serializable response generation
    - Replay mode for verification

    USAGE:
        adapter = MCPAdapter()

        # Live execution mode
        response = adapter.call(
            endpoint="https://api.example.com/data",
            method="GET",
            timeout_ms=5000,
        )

        # Replay mode (for verification)
        adapter.enable_replay_mode(cached_responses)
        response = adapter.call(...)  # Returns cached response
    """

    def __init__(
        self,
        retry_policy: Optional[RetryPolicy] = None,
        http_client: Optional[Any] = None,
    ):
        """
        Initialize MCP adapter.

        Args:
            retry_policy: Deterministic retry policy
            http_client: HTTP client for actual calls (None for mock mode)
        """
        self._retry_policy = retry_policy or RetryPolicy()
        self._http_client = http_client

        # Replay mode state
        self._replay_mode = False
        self._cached_responses: dict[str, MCPResponse] = {}

        # Call history for WAL
        self._call_history: list[tuple[MCPRequest, MCPResponse]] = []

    def enable_replay_mode(self, cached_responses: dict[str, dict]) -> None:
        """
        Enable replay mode with cached responses.

        In replay mode, actual network calls are not made.
        Instead, cached responses are returned based on request hash.

        Args:
            cached_responses: Map of request_hash -> response dict
        """
        self._replay_mode = True
        self._cached_responses = {
            k: MCPResponse(
                status_code=v["status_code"],
                response=v["response"],
                latency_metadata=LatencyMetadata(
                    duration_ms=v.get("latency_ms", 0),
                    timeout_ms=v.get("timeout_ms", 0),
                    did_timeout=v.get("did_timeout", False),
                ),
                request_hash=k,
                success=v.get("success", True),
            )
            for k, v in cached_responses.items()
        }

    def disable_replay_mode(self) -> None:
        """Disable replay mode and clear cached responses."""
        self._replay_mode = False
        self._cached_responses.clear()

    def call(
        self,
        endpoint: str,
        method: str,
        payload: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, Any]] = None,
        timeout_ms: int = 30000,
    ) -> dict[str, Any]:
        """
        Make external call via MCP protocol.

        Args:
            endpoint: Target URL
            method: HTTP method (GET, POST, PUT, DELETE)
            payload: Request body
            headers: Request headers
            timeout_ms: Timeout in milliseconds

        Returns:
            Serializable response dict with latency metadata

        Raises:
            MCPError: If call fails and retries exhausted
        """
        request = MCPRequest(
            endpoint=endpoint,
            method=method,
            payload=payload or {},
            headers=headers or {},
            timeout_ms=timeout_ms,
        )

        # Replay mode - return cached response
        if self._replay_mode:
            return self._replay_call(request)

        # Live mode - make actual call with retry
        return self._live_call(request)

    def _replay_call(self, request: MCPRequest) -> dict[str, Any]:
        """Handle call in replay mode."""
        request_hash = request.compute_hash()

        if request_hash not in self._cached_responses:
            raise MCPError(
                f"No cached response for request hash: {request_hash}. "
                "Replay mode requires all responses to be cached.",
                retry_reason=RetryReason.RUNTIME_ERROR,
                recoverable=False,
            )

        response = self._cached_responses[request_hash]
        self._call_history.append((request, response))

        return response.to_dict()

    def _live_call(self, request: MCPRequest) -> dict[str, Any]:
        """Handle call in live mode with retries."""
        retry_count = 0
        last_error: Optional[MCPError] = None

        while True:
            latency = LatencyMetadata(
                start_time=current_time_ms(),
                timeout_ms=request.timeout_ms,
            )

            try:
                response = self._execute_request(request, latency)
                self._call_history.append((request, response))
                return response.to_dict()

            except MCPError as e:
                last_error = e
                latency.end_time = current_time_ms()
                latency.duration_ms = latency.end_time - latency.start_time
                latency.did_timeout = (e.retry_reason == RetryReason.TIMEOUT)
                latency.retry_triggered = True

                if not self._retry_policy.should_retry(retry_count, e):
                    # Create error response for WAL
                    error_response = MCPResponse(
                        status_code=e.status_code,
                        response={},
                        latency_metadata=latency,
                        request_hash=request.compute_hash(),
                        success=False,
                        error_message=str(e),
                    )
                    self._call_history.append((request, error_response))
                    raise

                # Deterministic delay before retry
                delay_ms = self._retry_policy.get_delay(retry_count)
                time.sleep(delay_ms / 1000.0)
                retry_count += 1

    def _execute_request(
        self, request: MCPRequest, latency: LatencyMetadata
    ) -> MCPResponse:
        """
        Execute a single request attempt.

        This method handles the actual network call (or mock in test mode).
        """
        if self._http_client is None:
            # Mock mode - return simulated response
            return self._mock_request(request, latency)

        # Real HTTP call via configured client
        try:
            # Convert timeout to seconds for typical HTTP clients
            timeout_seconds = request.timeout_ms / 1000.0

            if request.method == "GET":
                result = self._http_client.get(
                    request.endpoint,
                    headers=request.headers,
                    timeout=timeout_seconds,
                )
            elif request.method == "POST":
                result = self._http_client.post(
                    request.endpoint,
                    json=request.payload,
                    headers=request.headers,
                    timeout=timeout_seconds,
                )
            elif request.method == "PUT":
                result = self._http_client.put(
                    request.endpoint,
                    json=request.payload,
                    headers=request.headers,
                    timeout=timeout_seconds,
                )
            elif request.method == "DELETE":
                result = self._http_client.delete(
                    request.endpoint,
                    headers=request.headers,
                    timeout=timeout_seconds,
                )
            else:
                raise MCPError(
                    f"Unsupported HTTP method: {request.method}",
                    retry_reason=RetryReason.RUNTIME_ERROR,
                    recoverable=False,
                )

            latency.end_time = current_time_ms()
            latency.duration_ms = latency.end_time - latency.start_time

            # Check for timeout
            if latency.duration_ms > request.timeout_ms:
                latency.did_timeout = True
                raise MCPError(
                    f"Request timed out after {latency.duration_ms}ms",
                    status_code=408,
                    retry_reason=RetryReason.TIMEOUT,
                    recoverable=True,
                )

            return MCPResponse(
                status_code=result.status_code,
                response=result.json() if result.text else {},
                latency_metadata=latency,
                request_hash=request.compute_hash(),
                success=result.status_code < 400,
            )

        except Exception as e:
            latency.end_time = current_time_ms()
            latency.duration_ms = latency.end_time - latency.start_time

            if "timeout" in str(e).lower():
                latency.did_timeout = True
                raise MCPError(
                    str(e),
                    status_code=408,
                    retry_reason=RetryReason.TIMEOUT,
                    recoverable=True,
                )
            else:
                raise MCPError(
                    str(e),
                    retry_reason=RetryReason.NETWORK_ERROR,
                    recoverable=True,
                )

    def _mock_request(
        self, request: MCPRequest, latency: LatencyMetadata
    ) -> MCPResponse:
        """
        Generate mock response for testing.

        Mock responses are deterministic based on request hash.
        """
        # Simulate some latency
        time.sleep(0.01)  # 10ms simulated latency

        latency.end_time = current_time_ms()
        latency.duration_ms = latency.end_time - latency.start_time

        # Generate deterministic mock response
        request_hash = request.compute_hash()
        mock_data = {
            "request_hash": request_hash,
            "endpoint": request.endpoint,
            "method": request.method,
            "mock": True,
            "timestamp": latency.start_time,
        }

        return MCPResponse(
            status_code=200,
            response=mock_data,
            latency_metadata=latency,
            request_hash=request_hash,
            success=True,
        )

    def get_call_history(self) -> list[tuple[dict, dict]]:
        """
        Get call history for WAL storage.

        Returns list of (request, response) dicts.
        """
        return [
            (req.to_dict(), resp.to_dict())
            for req, resp in self._call_history
        ]

    def clear_history(self) -> None:
        """Clear call history."""
        self._call_history.clear()

    def export_for_replay(self) -> dict[str, dict]:
        """
        Export call history as cached responses for replay.

        Returns map of request_hash -> response for replay mode.
        """
        return {
            req.compute_hash(): resp.to_dict()
            for req, resp in self._call_history
        }


def create_mcp_adapter(
    max_retries: int = 3,
    base_delay_ms: int = 1000,
    http_client: Optional[Any] = None,
) -> MCPAdapter:
    """
    Factory function to create configured MCP adapter.

    Args:
        max_retries: Maximum retry attempts
        base_delay_ms: Base delay between retries
        http_client: HTTP client (None for mock mode)

    Returns:
        Configured MCPAdapter instance
    """
    retry_policy = RetryPolicy(
        max_retries=max_retries,
        base_delay_ms=base_delay_ms,
    )

    return MCPAdapter(
        retry_policy=retry_policy,
        http_client=http_client,
    )
