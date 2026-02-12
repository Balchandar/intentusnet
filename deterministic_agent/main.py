"""
IntentusNet v1.4.1 Deterministic Agent - Main Runtime

Production-grade deterministic agent with:
- State-safe, replay-verifiable execution
- Zero logic regressions
- Exact-once side-effect safety
- Fully debuggable deterministic execution via WAL logs

This is the main entry point for the deterministic agent runtime.

CRITICAL GUARANTEES:
1. Deterministic execution - same input always produces same output
2. Replay equivalence - execution can be replayed for verification
3. Exact-once side-effects - state-changing tools never re-execute
4. Deterministic recovery - failures resume from last committed step
5. CI-verified logic stability - fingerprints detect any drift
6. Full execution fingerprinting - complete audit trail
7. Deterministic external tools - MCP adapters enforce replay safety

USAGE:
    # Initialize runtime
    runtime = DeterministicAgentRuntime(
        wal_dir="./logs",
        tool_registry=create_default_registry(mcp_adapter),
    )

    # Execute intent
    result = runtime.execute(
        intent="process_order",
        params={"order_id": "12345"},
    )

    # Get execution fingerprint
    print(f"Fingerprint: {result.fingerprint}")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, List
from uuid import uuid4

from .models import (
    WALEntry,
    ExecutionFingerprint,
    SideEffectClass,
    RetryReason,
    LatencyMetadata,
    DriftClassification,
    compute_params_hash,
    compute_output_hash,
    current_time_ms,
)
from .tool_registry import (
    ToolRegistry,
    BaseTool,
    ToolExecutionError,
    create_default_registry,
)
from .mcp_adapter import MCPAdapter, MCPError, create_mcp_adapter
from .wal_engine import WALWriter, WALReader, WALState, WALIntegrityError
from .recovery_engine import (
    RecoveryEngine,
    RecoveryManager,
    RecoveryDecision,
    RecoveryAnalysis,
)

logger = logging.getLogger("intentusnet.deterministic_agent")


@dataclass
class ExecutionStep:
    """
    Definition of an execution step in the agent workflow.

    Each step specifies:
    - Intent name
    - Tool to execute
    - Parameters to pass
    - Timeout configuration
    """
    intent: str
    tool_name: str
    params: dict[str, Any]
    timeout_ms: int = 30000

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "tool_name": self.tool_name,
            "params": self.params,
            "timeout_ms": self.timeout_ms,
        }


@dataclass
class ExecutionResult:
    """
    Result of deterministic execution.

    Contains:
    - Success status
    - Execution outputs
    - Fingerprint for verification
    - WAL path for debugging
    - Timing metrics
    """
    success: bool
    execution_id: str
    outputs: list[Any] = field(default_factory=list)
    fingerprint: str = ""
    wal_path: str = ""
    error: Optional[str] = None
    step_count: int = 0
    total_duration_ms: int = 0
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "execution_id": self.execution_id,
            "outputs": self.outputs,
            "fingerprint": self.fingerprint,
            "wal_path": self.wal_path,
            "error": self.error,
            "step_count": self.step_count,
            "total_duration_ms": self.total_duration_ms,
            "retry_count": self.retry_count,
        }


class DeterministicAgentRuntime:
    """
    Deterministic Agent Runtime with WAL-backed execution.

    This runtime provides production-grade guarantees for AI agent execution:

    1. DETERMINISTIC EXECUTION
       - No randomness in tool selection
       - Fixed execution order
       - Reproducible parameter handling

    2. REPLAY EQUIVALENCE
       - Full WAL logging of all steps
       - Execution fingerprint computation
       - Verification via replay engine

    3. EXACT-ONCE SIDE-EFFECTS
       - Idempotency keys for state-changing tools
       - WAL commit before side-effect execution
       - Never re-run committed state-changing steps

    4. DETERMINISTIC RECOVERY
       - Resume from last committed step
       - Preserve execution fingerprint
       - Abort if safe threshold exceeded

    5. MCP-ONLY EXTERNAL CALLS
       - All external tools via MCP adapter
       - Normalized timeouts
       - Captured latency metadata

    USAGE:
        runtime = DeterministicAgentRuntime(
            wal_dir="./logs",
            tool_registry=registry,
        )

        # Define execution steps
        steps = [
            ExecutionStep(
                intent="fetch_data",
                tool_name="fetch_context",
                params={"context_key": "user_123"},
            ),
            ExecutionStep(
                intent="update_record",
                tool_name="update_database",
                params={"table": "users", "record_id": "123", "data": {...}},
            ),
        ]

        # Execute deterministically
        result = runtime.execute_steps(steps)

        print(f"Fingerprint: {result.fingerprint}")
    """

    def __init__(
        self,
        wal_dir: str = "./logs",
        tool_registry: Optional[ToolRegistry] = None,
        mcp_adapter: Optional[MCPAdapter] = None,
        max_retries: int = 3,
        abort_on_side_effect_drift: bool = True,
    ):
        """
        Initialize deterministic agent runtime.

        Args:
            wal_dir: Directory for WAL files
            tool_registry: Registry of available tools
            mcp_adapter: MCP adapter for external calls
            max_retries: Maximum retries for recoverable errors
            abort_on_side_effect_drift: Abort if side-effect drift detected
        """
        self.wal_dir = Path(wal_dir)
        self.wal_dir.mkdir(parents=True, exist_ok=True)

        # Initialize MCP adapter if not provided
        self.mcp_adapter = mcp_adapter or create_mcp_adapter()

        # Initialize tool registry with MCP adapter
        self.tool_registry = tool_registry or create_default_registry(
            mcp_adapter=self.mcp_adapter
        )

        self.max_retries = max_retries
        self.abort_on_side_effect_drift = abort_on_side_effect_drift

        # Recovery manager
        self.recovery_manager = RecoveryManager(str(self.wal_dir))

        logger.info(
            f"Initialized DeterministicAgentRuntime v1.4.1 "
            f"(wal_dir={self.wal_dir}, tools={self.tool_registry.list_tools()})"
        )

    def execute_steps(
        self,
        steps: list[ExecutionStep],
        execution_id: Optional[str] = None,
    ) -> ExecutionResult:
        """
        Execute a sequence of steps deterministically.

        Args:
            steps: List of execution steps
            execution_id: Optional execution ID (generated if not provided)

        Returns:
            ExecutionResult with outputs and fingerprint
        """
        execution_id = execution_id or str(uuid4())
        wal_path = self.wal_dir / f"{execution_id}.jsonl"
        start_time = current_time_ms()

        logger.info(f"Starting execution {execution_id} with {len(steps)} steps")

        # Check for recovery
        if wal_path.exists():
            analysis = self.recovery_manager.engine.analyze(execution_id)

            if analysis.decision == RecoveryDecision.COMPLETE:
                logger.info(f"Execution {execution_id} already completed")
                return self._load_completed_result(execution_id, str(wal_path))

            elif analysis.decision == RecoveryDecision.RESUME:
                logger.info(f"Resuming execution {execution_id} from step {analysis.can_resume_from}")
                return self._resume_execution(
                    execution_id, steps, analysis, start_time
                )

            elif analysis.decision == RecoveryDecision.ABORT:
                logger.error(f"Execution {execution_id} cannot be recovered: {analysis.reason}")
                return ExecutionResult(
                    success=False,
                    execution_id=execution_id,
                    wal_path=str(wal_path),
                    error=f"Recovery failed: {analysis.reason}",
                )

        # Fresh execution
        return self._execute_fresh(execution_id, steps, start_time)

    def _execute_fresh(
        self,
        execution_id: str,
        steps: list[ExecutionStep],
        start_time: int,
    ) -> ExecutionResult:
        """Execute steps from beginning."""
        wal_path = self.wal_dir / f"{execution_id}.jsonl"
        outputs = []
        fingerprint = ExecutionFingerprint(execution_id=execution_id)
        total_retries = 0

        try:
            with WALWriter(str(wal_path), execution_id) as wal:
                for idx, step in enumerate(steps):
                    output, retries = self._execute_step(
                        wal, step, idx + 1, fingerprint
                    )
                    outputs.append(output)
                    total_retries += retries

                # Finalize and compute fingerprint
                final_fingerprint = wal.finalize()

        except Exception as e:
            logger.exception(f"Execution {execution_id} failed")
            return ExecutionResult(
                success=False,
                execution_id=execution_id,
                outputs=outputs,
                wal_path=str(wal_path),
                error=str(e),
                step_count=len(outputs),
                total_duration_ms=current_time_ms() - start_time,
                retry_count=total_retries,
            )

        return ExecutionResult(
            success=True,
            execution_id=execution_id,
            outputs=outputs,
            fingerprint=final_fingerprint,
            wal_path=str(wal_path),
            step_count=len(outputs),
            total_duration_ms=current_time_ms() - start_time,
            retry_count=total_retries,
        )

    def _resume_execution(
        self,
        execution_id: str,
        steps: list[ExecutionStep],
        analysis: RecoveryAnalysis,
        start_time: int,
    ) -> ExecutionResult:
        """Resume execution from last committed step."""
        wal_path = self.wal_dir / f"{execution_id}.jsonl"
        resume_from = analysis.can_resume_from
        idempotency_keys = analysis.idempotency_keys

        # Load outputs from completed steps
        outputs = self._load_committed_outputs(execution_id)
        fingerprint = ExecutionFingerprint(execution_id=execution_id)
        total_retries = 0

        try:
            with WALWriter(str(wal_path), execution_id) as wal:
                # Restore state
                wal._state.idempotency_keys = idempotency_keys
                wal._state.committed_steps = list(analysis.wal_state.committed_steps)

                # Execute remaining steps
                for idx, step in enumerate(steps):
                    step_order = idx + 1

                    # Skip already committed steps
                    if step_order < resume_from:
                        continue

                    output, retries = self._execute_step(
                        wal, step, step_order, fingerprint
                    )
                    outputs.append(output)
                    total_retries += retries

                # Finalize
                final_fingerprint = wal.finalize()

        except Exception as e:
            logger.exception(f"Resumed execution {execution_id} failed")
            return ExecutionResult(
                success=False,
                execution_id=execution_id,
                outputs=outputs,
                wal_path=str(wal_path),
                error=str(e),
                step_count=len(outputs),
                total_duration_ms=current_time_ms() - start_time,
                retry_count=total_retries,
            )

        return ExecutionResult(
            success=True,
            execution_id=execution_id,
            outputs=outputs,
            fingerprint=final_fingerprint,
            wal_path=str(wal_path),
            step_count=len(outputs),
            total_duration_ms=current_time_ms() - start_time,
            retry_count=total_retries,
        )

    def _execute_step(
        self,
        wal: WALWriter,
        step: ExecutionStep,
        execution_order: int,
        fingerprint: ExecutionFingerprint,
    ) -> tuple[Any, int]:
        """
        Execute a single step with WAL logging.

        Returns:
            Tuple of (output, retry_count)
        """
        tool = self.tool_registry.get_required(step.tool_name)
        side_effect_class = tool.schema.side_effect_class
        max_retries = tool.schema.max_retries if side_effect_class != SideEffectClass.STATE_CHANGING else 0

        retry_count = 0
        retry_reason = RetryReason.NONE
        last_error: Optional[Exception] = None

        while retry_count <= max_retries:
            # Log step started BEFORE execution
            wal_entry = wal.log_step_started(
                intent=step.intent,
                tool_name=step.tool_name,
                params=step.params,
                side_effect_class=side_effect_class,
                timeout_ms=step.timeout_ms,
            )

            try:
                # Execute tool
                start = current_time_ms()
                output = tool.execute(step.params)
                end = current_time_ms()

                # Update latency metadata
                wal_entry.latency_metadata.end_time = end
                wal_entry.latency_metadata.duration_ms = end - start

                # Check timeout
                if wal_entry.latency_metadata.duration_ms > step.timeout_ms:
                    wal_entry.latency_metadata.did_timeout = True
                    raise ToolExecutionError(
                        f"Tool execution timed out after {wal_entry.latency_metadata.duration_ms}ms",
                        retry_reason=RetryReason.TIMEOUT,
                        recoverable=(side_effect_class != SideEffectClass.STATE_CHANGING),
                    )

                # Commit step AFTER successful execution
                completed_entry = wal.commit_step(
                    wal_entry.step_id,
                    output,
                    retry_count=retry_count,
                    retry_reason=retry_reason,
                )

                # Add to fingerprint
                completed_entry.intent = step.intent
                completed_entry.tool_name = step.tool_name
                completed_entry.params_hash = compute_params_hash(step.params)
                completed_entry.side_effect_class = side_effect_class
                completed_entry.latency_metadata = wal_entry.latency_metadata
                wal.add_to_fingerprint(completed_entry)

                logger.info(
                    f"Step {execution_order} completed: {step.tool_name} "
                    f"(duration={wal_entry.latency_metadata.duration_ms}ms, retries={retry_count})"
                )

                return output, retry_count

            except ToolExecutionError as e:
                last_error = e
                retry_reason = e.retry_reason

                # Log failure
                wal.log_step_failed(
                    wal_entry.step_id,
                    str(e),
                    retry_reason=e.retry_reason,
                    recoverable=e.recoverable,
                )

                # Don't retry if not recoverable or state-changing
                if not e.recoverable or side_effect_class == SideEffectClass.STATE_CHANGING:
                    raise

                retry_count += 1
                logger.warning(
                    f"Step {execution_order} failed (attempt {retry_count}/{max_retries + 1}): {e}"
                )

                # Exponential backoff
                if retry_count <= max_retries:
                    time.sleep(min(2 ** retry_count, 30))

            except Exception as e:
                last_error = e
                wal.log_step_failed(
                    wal_entry.step_id,
                    str(e),
                    retry_reason=RetryReason.RUNTIME_ERROR,
                    recoverable=False,
                )
                raise

        # Max retries exceeded
        raise ToolExecutionError(
            f"Max retries ({max_retries}) exceeded: {last_error}",
            retry_reason=retry_reason,
            recoverable=False,
        )

    def _load_completed_result(
        self,
        execution_id: str,
        wal_path: str,
    ) -> ExecutionResult:
        """Load result from completed execution."""
        reader = WALReader(wal_path)
        reader.load()

        fingerprint = reader.get_fingerprint()
        outputs = self._load_committed_outputs(execution_id)

        return ExecutionResult(
            success=True,
            execution_id=execution_id,
            outputs=outputs,
            fingerprint=fingerprint or "",
            wal_path=wal_path,
            step_count=len(outputs),
        )

    def _load_committed_outputs(self, execution_id: str) -> list[Any]:
        """Load outputs from committed steps."""
        wal_path = self.wal_dir / f"{execution_id}.jsonl"
        reader = WALReader(str(wal_path))
        reader.load()

        outputs = []
        for entry in reader.get_entries():
            if entry.get("entry_type") == "step.committed":
                outputs.append(entry.get("output_snapshot"))

        return outputs

    def execute(
        self,
        intent: str,
        params: dict[str, Any],
        tool_name: Optional[str] = None,
    ) -> ExecutionResult:
        """
        Execute a single intent.

        Convenience method for single-step execution.

        Args:
            intent: Intent name
            params: Intent parameters
            tool_name: Optional tool name (defaults to intent name)

        Returns:
            ExecutionResult
        """
        step = ExecutionStep(
            intent=intent,
            tool_name=tool_name or intent,
            params=params,
        )
        return self.execute_steps([step])


def create_runtime(
    wal_dir: str = "./logs",
    mcp_adapter: Optional[MCPAdapter] = None,
) -> DeterministicAgentRuntime:
    """
    Factory function to create deterministic runtime.

    Args:
        wal_dir: WAL directory path
        mcp_adapter: Optional MCP adapter

    Returns:
        Configured DeterministicAgentRuntime
    """
    return DeterministicAgentRuntime(
        wal_dir=wal_dir,
        mcp_adapter=mcp_adapter,
    )


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import argparse
    import json
    import sys

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="IntentusNet v1.4.1 Deterministic Agent Runtime"
    )
    parser.add_argument(
        "--wal-dir",
        default="./logs",
        help="WAL directory path",
    )
    parser.add_argument(
        "--execution-id",
        help="Execution ID (generated if not provided)",
    )
    parser.add_argument(
        "--steps-file",
        help="JSON file containing execution steps",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="List available tools",
    )
    parser.add_argument(
        "--list-incomplete",
        action="store_true",
        help="List incomplete executions",
    )
    parser.add_argument(
        "--recover",
        metavar="EXECUTION_ID",
        help="Attempt to recover execution",
    )

    args = parser.parse_args()

    # Create runtime
    runtime = create_runtime(wal_dir=args.wal_dir)

    if args.list_tools:
        print("Available tools:")
        for schema in runtime.tool_registry.export_schemas():
            print(f"  - {schema['name']}: {schema['description']}")
            print(f"    Side-effect: {schema['side_effect_class']}")
            print(f"    Timeout: {schema['timeout_ms']}ms")
            print()
        sys.exit(0)

    if args.list_incomplete:
        incomplete = runtime.recovery_manager.list_incomplete()
        if incomplete:
            print("Incomplete executions:")
            for analysis in incomplete:
                print(f"  - {analysis['execution_id']}: {analysis['decision']}")
                print(f"    Reason: {analysis['reason']}")
                print()
        else:
            print("No incomplete executions found.")
        sys.exit(0)

    if args.recover:
        info = runtime.recovery_manager.get_recovery_info(args.recover)
        print(f"Recovery info for {args.recover}:")
        print(json.dumps(info, indent=2))
        sys.exit(0)

    if args.steps_file:
        with open(args.steps_file, "r") as f:
            steps_data = json.load(f)

        steps = [ExecutionStep(**s) for s in steps_data]
        result = runtime.execute_steps(steps, execution_id=args.execution_id)

        print(json.dumps(result.to_dict(), indent=2))
        sys.exit(0 if result.success else 1)

    # Demo execution
    print("Running demo execution...")

    steps = [
        ExecutionStep(
            intent="fetch_user_context",
            tool_name="fetch_context",
            params={"context_key": "user_123", "include_metadata": True},
        ),
        ExecutionStep(
            intent="update_user_record",
            tool_name="update_database",
            params={
                "table": "users",
                "record_id": "123",
                "data": {"last_login": "2026-02-09T10:00:00Z"},
            },
        ),
    ]

    result = runtime.execute_steps(steps)
    print(json.dumps(result.to_dict(), indent=2))
