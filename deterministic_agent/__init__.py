"""
IntentusNet v1.4.1 Deterministic Reliability Runtime

Production-grade deterministic agent with:
- State-safe, replay-verifiable execution
- Zero logic regressions
- Exact-once side-effect safety
- Fully debuggable deterministic execution via WAL logs

This module provides a complete deterministic agent infrastructure for
building reliable AI agents with Claude 3.5 Sonnet.

CORE GUARANTEES:
1. Deterministic execution
2. Replay equivalence
3. Exact-once side-effects
4. Deterministic recovery from failures
5. CI-verified logic stability
6. Full execution fingerprinting
7. Deterministic external tool behavior (timeout & latency safe)

USAGE:
    from deterministic_agent import (
        DeterministicAgentRuntime,
        ExecutionStep,
        create_runtime,
        create_mcp_adapter,
    )

    # Create runtime
    runtime = create_runtime(wal_dir="./logs")

    # Define steps
    steps = [
        ExecutionStep(
            intent="fetch_data",
            tool_name="fetch_context",
            params={"key": "value"},
        ),
    ]

    # Execute deterministically
    result = runtime.execute_steps(steps)

    print(f"Fingerprint: {result.fingerprint}")
"""

__version__ = "1.4.1"

# Core models
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

# Tool registry
from .tool_registry import (
    ToolSchema,
    BaseTool,
    ToolRegistry,
    ToolExecutionError,
    FetchContextTool,
    UpdateDatabaseTool,
    ExternalAPICallTool,
    create_default_registry,
)

# MCP adapter
from .mcp_adapter import (
    MCPAdapter,
    MCPRequest,
    MCPResponse,
    MCPError,
    RetryPolicy,
    create_mcp_adapter,
)

# WAL engine
from .wal_engine import (
    WALWriter,
    WALReader,
    WALState,
    WALIntegrityError,
    WALWriteError,
)

# Recovery engine
from .recovery_engine import (
    RecoveryEngine,
    RecoveryManager,
    RecoveryDecision,
    RecoveryAnalysis,
    RecoveryResult,
    create_recovery_manager,
)

# Main runtime
from .main import (
    DeterministicAgentRuntime,
    ExecutionStep,
    ExecutionResult,
    create_runtime,
)

# Replay engine
from .replay_engine import (
    ReplayEngine,
    ReplayExecution,
    ReplayStep,
    DiffResult,
    create_replay_engine,
)

# Evaluation rig
from .eval_agent import (
    EvaluationRig,
    EvaluationReport,
    TestCase,
    TestResult,
    create_evaluation_rig,
)

__all__ = [
    # Version
    "__version__",

    # Core models
    "WALEntry",
    "ExecutionFingerprint",
    "SideEffectClass",
    "RetryReason",
    "LatencyMetadata",
    "DriftClassification",
    "compute_params_hash",
    "compute_output_hash",
    "current_time_ms",

    # Tool registry
    "ToolSchema",
    "BaseTool",
    "ToolRegistry",
    "ToolExecutionError",
    "FetchContextTool",
    "UpdateDatabaseTool",
    "ExternalAPICallTool",
    "create_default_registry",

    # MCP adapter
    "MCPAdapter",
    "MCPRequest",
    "MCPResponse",
    "MCPError",
    "RetryPolicy",
    "create_mcp_adapter",

    # WAL engine
    "WALWriter",
    "WALReader",
    "WALState",
    "WALIntegrityError",
    "WALWriteError",

    # Recovery engine
    "RecoveryEngine",
    "RecoveryManager",
    "RecoveryDecision",
    "RecoveryAnalysis",
    "RecoveryResult",
    "create_recovery_manager",

    # Main runtime
    "DeterministicAgentRuntime",
    "ExecutionStep",
    "ExecutionResult",
    "create_runtime",

    # Replay engine
    "ReplayEngine",
    "ReplayExecution",
    "ReplayStep",
    "DiffResult",
    "create_replay_engine",

    # Evaluation rig
    "EvaluationRig",
    "EvaluationReport",
    "TestCase",
    "TestResult",
    "create_evaluation_rig",
]
