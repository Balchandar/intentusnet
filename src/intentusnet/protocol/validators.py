"""
IntentusNet Protocol Schema Validators
--------------------------------------

This module validates all protocol-level entities using JSON Schema.

JSON Schemas are stored in:
    intentusnet/protocol/schemas/*.json

This module is intentionally:
- decoupled from dataclasses (works on raw dict/JSON),
- split by protocol context (intent, agent, response, transport, emcl),
- ready for multi-language SDK consumption (same schemas shared).
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Dict, Mapping

from importlib import resources

import jsonschema


# ---------------------------------------------------------------------------
# Schema file mapping
# ---------------------------------------------------------------------------

# These are the canonical schema file names expected under
# intentusnet/protocol/schemas/
#
# You can adjust the actual file names as long as these constants match.
INTENT_ENVELOPE_SCHEMA = "intent_envelope.json"
AGENT_DEFINITION_SCHEMA = "agent_definition.json"
AGENT_RESPONSE_SCHEMA = "agent_response.json"
TRANSPORT_ENVELOPE_SCHEMA = "transport_envelope.json"
EMCL_ENVELOPE_SCHEMA = "emcl_envelope.json"
TRACE_SPAN_SCHEMA = "trace_span.json"
ROUTER_DECISION_SCHEMA = "router_decision.json"


SCHEMA_PACKAGE = "intentusnet.protocol.schemas"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _load_schema(schema_file: str) -> Dict[str, Any]:
    """
    Load a JSON schema from the protocol.schemas package.

    Uses importlib.resources so it works both from source and from wheels.
    """
    try:
        schema_path = resources.files(SCHEMA_PACKAGE).joinpath(schema_file)
    except AttributeError:
        # Python < 3.9 fallback (not really needed for 3.11, but safe)
        with resources.open_text(SCHEMA_PACKAGE, schema_file, encoding="utf-8") as f:
            return json.load(f)

    with schema_path.open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def _get_validator(schema_file: str) -> jsonschema.Validator:
    """
    Return a cached jsonschema Validator for the given schema file.
    """
    schema = _load_schema(schema_file)
    return jsonschema.Draft202012Validator(schema)


def _validate(schema_file: str, obj: Mapping[str, Any]) -> None:
    """
    Core validation helper that raises jsonschema.ValidationError
    on failure.
    """
    validator = _get_validator(schema_file)
    validator.validate(obj)  # raises on error


# ---------------------------------------------------------------------------
# Public validation functions (per protocol context)
# ---------------------------------------------------------------------------

def validate_intent_envelope(obj: Mapping[str, Any]) -> None:
    """
    Validate an IntentEnvelope dict against intent_envelope.json.

    Expected shape (high-level):
        {
          "version": "1.0",
          "intent": {...},
          "payload": {...},
          "context": {...},
          "metadata": {...},
          "routing": {...},
          "routingMetadata": {...}
        }
    """
    _validate(INTENT_ENVELOPE_SCHEMA, obj)


def validate_agent_definition(obj: Mapping[str, Any]) -> None:
    """
    Validate an AgentDefinition dict against agent_definition.json.

    Expected shape (high-level):
        {
          "name": "...",
          "version": "...",
          "identity": {...},
          "capabilities": [...],
          "endpoint": {...},
          "health": {...},
          "runtime": {...}
        }
    """
    _validate(AGENT_DEFINITION_SCHEMA, obj)


def validate_agent_response(obj: Mapping[str, Any]) -> None:
    """
    Validate an AgentResponse dict against agent_response.json.

    Expected shape (high-level):
        {
          "version": "1.0",
          "status": "success" | "error",
          "payload": {...} | null,
          "metadata": {...},
          "error": {...} | null
        }
    """
    _validate(AGENT_RESPONSE_SCHEMA, obj)


def validate_transport_envelope(obj: Mapping[str, Any]) -> None:
    """
    Validate a TransportEnvelope dict against transport_envelope.json.

    Expected shape (high-level):
        {
          "version": "1.0",
          "body": {...},
          "metadata": {...},
          "isEncrypted": false | true
        }
    """
    _validate(TRANSPORT_ENVELOPE_SCHEMA, obj)


def validate_emcl_envelope(obj: Mapping[str, Any]) -> None:
    """
    Validate an EMCLEnvelope dict against emcl_envelope.json.

    Expected shape (high-level):
        {
          "cipherText": "...",
          "iv": "...",
          "tag": "...",
          "identityChain": [...]
        }
    """
    _validate(EMCL_ENVELOPE_SCHEMA, obj)


def validate_trace_span(obj: Mapping[str, Any]) -> None:
    """
    Validate a TraceSpan dict against trace_span.json.
    """
    _validate(TRACE_SPAN_SCHEMA, obj)


def validate_router_decision(obj: Mapping[str, Any]) -> None:
    """
    Validate a RouterDecision dict against router_decision.json.
    """
    _validate(ROUTER_DECISION_SCHEMA, obj)


# ---------------------------------------------------------------------------
# Debug helper
# ---------------------------------------------------------------------------

def debug_validate(schema_file: str, obj: Mapping[str, Any]) -> None:
    """
    Print human-readable validation errors for debugging.

    Does NOT raise — just prints errors to stdout.
    """
    validator = _get_validator(schema_file)
    errors = sorted(validator.iter_errors(obj), key=lambda e: e.path)

    if not errors:
        print(f"[OK] {schema_file}")
        return

    print(f"[ERROR] Validation failed for {schema_file}:")
    for e in errors:
        print(f"• path={list(e.path)} → {e.message}")
