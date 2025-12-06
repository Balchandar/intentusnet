"""
IntentusNet Protocol Schema Validators
--------------------------------------

This module validates all protocol-level entities using JSON Schema.

Flexible JSON Schemas are stored in:
intentusnet/protocol/schemas/*.json

All schemas are loaded once and cached for performance.
"""

from __future__ import annotations
import json
import os
from functools import lru_cache
from typing import Any, Dict

from jsonschema import Draft202012Validator, ValidationError

from .errors import IntentusError, EMCLValidationError


# Schema loading utilities

SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "schemas")


def _load_json(path: str) -> Dict[str, Any]:
    """Load a JSON file from disk."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=32)
def _load_schema(name: str) -> Dict[str, Any]:
    """Load and cache a JSON schema by filename."""
    full_path = os.path.join(SCHEMA_DIR, name)
    if not os.path.exists(full_path):
        raise FileNotFoundError(f"Schema file not found: {full_path}")

    return _load_json(full_path)


@lru_cache(maxsize=32)
def _get_validator(name: str) -> Draft202012Validator:
    """Return a compiled JSON Schema validator."""
    schema = _load_schema(name)
    return Draft202012Validator(schema)


# Core validation wrapper

def _validate(obj: Dict[str, Any], schema_file: str, error_cls=IntentusError) -> None:
    """Generic validator wrapper that throws IntentusError or EMCLValidationError."""
    validator = _get_validator(schema_file)

    try:
        validator.validate(obj)
    except ValidationError as e:
        raise error_cls(
            f"Validation failed for schema '{schema_file}': {e.message}"
        ) from e


# Public validation functions

def validate_intent_definition(data: Dict[str, Any]) -> None:
    """
    Validate an Intent Definition structure.
    """
    _validate(data, "intent_definition.json", IntentusError)


def validate_intent_envelope(data: Dict[str, Any]) -> None:
    """
    Validate an IntentEnvelope before routing.
    """
    _validate(data, "intent_envelope.json", IntentusError)


def validate_agent_definition(data: Dict[str, Any]) -> None:
    """
    Validate an AgentDefinition before registry registration.
    """
    _validate(data, "agent_definition.json", IntentusError)


def validate_agent_response(data: Dict[str, Any]) -> None:
    """
    Validate an AgentResponse emitted from an agent.
    """
    _validate(data, "response.json", IntentusError)


def validate_transport_envelope(data: Dict[str, Any]) -> None:
    """
    Validate a TransportEnvelope before sending through transports.
    """
    _validate(data, "transport_envelope.json", IntentusError)


def validate_emcl_envelope(data: Dict[str, Any]) -> None:
    """
    Validate an EMCL envelope before decrypting or forwarding.

    Note: This uses EMCLValidationError.
    """
    _validate(data, "emcl_envelope.json", EMCLValidationError)


# Optional: utility for debugging validation

def debug_validate(obj: Dict[str, Any], schema_file: str) -> None:
    """
    Print human-readable validation errors for debugging.
    Does NOT raise — just prints.
    """
    validator = _get_validator(schema_file)
    errors = sorted(validator.iter_errors(obj), key=lambda e: e.path)

    if not errors:
        print(f"[OK] {schema_file}")
        return

    print(f"[ERROR] Validation failed for {schema_file}:")
    for e in errors:
        print(f"• {list(e.path)} → {e.message}")
