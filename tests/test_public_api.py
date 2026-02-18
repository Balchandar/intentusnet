"""
Test suite for public API exports (Improvement #1).

Verifies that all exports in __all__ are actually importable
and fixes the broken IntentEnvelope import.
"""

import pytest


def test_all_exports_are_importable():
    """Verify every item in __all__ can be imported."""
    import intentusnet

    for name in intentusnet.__all__:
        assert hasattr(intentusnet, name), f"{name} in __all__ but not importable"


def test_intent_envelope_import():
    """
    Regression test for broken IntentEnvelope import.

    Bug: IntentEnvelope was in __all__ but not imported,
    causing AttributeError when users tried to import it.
    """
    from intentusnet import IntentEnvelope

    assert IntentEnvelope is not None
    # Verify it's a dataclass
    assert hasattr(IntentEnvelope, "__dataclass_fields__")


def test_version_export():
    """Verify __version__ is available."""
    import intentusnet

    assert hasattr(intentusnet, "__version__")
    assert intentusnet.__version__ == "1.5.1"
    assert isinstance(intentusnet.__version__, str)


def test_recording_exports():
    """Verify recording components are exported (were missing before)."""
    from intentusnet import ExecutionRecord, ReplayEngine, FileExecutionStore

    assert all([ExecutionRecord, ReplayEngine, FileExecutionStore])


def test_enum_exports():
    """Verify enums are exported (were missing before)."""
    from intentusnet import Priority, RoutingStrategy, ErrorCode

    assert all([Priority, RoutingStrategy, ErrorCode])

    # Verify they're actual enums
    from enum import Enum
    assert issubclass(Priority, Enum)
    assert issubclass(RoutingStrategy, Enum)
    assert issubclass(ErrorCode, Enum)


def test_protocol_type_exports():
    """Verify protocol types are exported."""
    from intentusnet import (
        IntentRef,
        IntentContext,
        IntentMetadata,
        RoutingOptions,
        ErrorInfo,
    )

    assert all([IntentRef, IntentContext, IntentMetadata, RoutingOptions, ErrorInfo])


def test_tracing_exports():
    """Verify tracing types are exported (were missing before)."""
    from intentusnet import TraceSink, RouterDecision, TraceSpan

    assert all([TraceSink, RouterDecision, TraceSpan])


def test_core_runtime_exports():
    """Verify core runtime components are exported."""
    from intentusnet import (
        IntentusRuntime,
        IntentRouter,
        AgentRegistry,
        IntentusClient,
        BaseAgent,
    )

    assert all([IntentusRuntime, IntentRouter, AgentRegistry, IntentusClient, BaseAgent])


def test_intent_envelope_can_be_constructed():
    """Verify IntentEnvelope can be constructed (end-to-end check)."""
    from intentusnet import IntentEnvelope, IntentRef, IntentContext, IntentMetadata, RoutingOptions

    envelope = IntentEnvelope(
        version="1.0",
        intent=IntentRef(name="TestIntent", version="1.0"),
        payload={"test": "data"},
        context=IntentContext(
            sourceAgent="test",
            timestamp="2026-01-02T00:00:00Z",
        ),
        metadata=IntentMetadata(
            requestId="req-123",
            source="test",
            createdAt="2026-01-02T00:00:00Z",
            traceId="trace-123",
        ),
        routing=RoutingOptions(),
    )

    assert envelope.intent.name == "TestIntent"
    assert envelope.payload == {"test": "data"}


def test_priority_enum_values():
    """Verify Priority enum has expected values."""
    from intentusnet import Priority

    assert Priority.LOW.value == "low"
    assert Priority.NORMAL.value == "normal"
    assert Priority.HIGH.value == "high"


def test_routing_strategy_enum_values():
    """Verify RoutingStrategy enum has expected values."""
    from intentusnet import RoutingStrategy

    assert RoutingStrategy.DIRECT.value == "direct"
    assert RoutingStrategy.FALLBACK.value == "fallback"
    assert RoutingStrategy.BROADCAST.value == "broadcast"
    assert RoutingStrategy.PARALLEL.value == "parallel"


def test_error_code_enum_values():
    """Verify ErrorCode enum has expected values."""
    from intentusnet import ErrorCode

    # Spot check a few critical error codes
    assert ErrorCode.VALIDATION_ERROR.value == "VALIDATION_ERROR"
    assert ErrorCode.ROUTING_ERROR.value == "ROUTING_ERROR"
    assert ErrorCode.CAPABILITY_NOT_FOUND.value == "CAPABILITY_NOT_FOUND"


def test_no_missing_imports():
    """
    Verify there are no items in __all__ that raise ImportError.

    This is a stronger test than just checking hasattr.
    """
    import intentusnet

    for name in intentusnet.__all__:
        try:
            obj = getattr(intentusnet, name)
            assert obj is not None
        except AttributeError as e:
            pytest.fail(f"Failed to import {name}: {e}")
