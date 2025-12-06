"""
ID generators used across IntentusNet:
- UUID v4
- Short random IDs
- ULID (Universally Unique Lexicographically Sortable Identifier)
"""

from __future__ import annotations
import uuid
import os
import base64
import time


def generate_uuid() -> str:
    """Generate a UUIDv4 string."""
    return str(uuid.uuid4())


def generate_short_id(byte_length: int = 6) -> str:
    """
    Generate a short, URL-safe random ID.
    Default: 6 bytes → 8 char string
    """
    return base64.urlsafe_b64encode(os.urandom(byte_length)).decode("utf-8").rstrip("=")


def generate_ulid() -> str:
    """
    Generate a ULID string (no external dependency).
    Used for traceIds, correlationIds, etc.
    """
    # timestamp part (48 bits)
    timestamp_ms = int(time.time() * 1000)
    ts_bytes = timestamp_ms.to_bytes(6, byteorder="big")

    # randomness part (80 bits)
    entropy = os.urandom(10)

    encoded = base64.b32encode(ts_bytes + entropy).decode("utf-8")
    return encoded.replace("=", "").lower()
