"""
CLI security guardrails.

Minimal security for production CLI operations.
"""

from __future__ import annotations

import os
import sys
from typing import Optional
from enum import Enum


class CLIMode(str, Enum):
    """CLI operation mode."""
    READ_WRITE = "read_write"
    READ_ONLY = "read_only"


class SecurityGuard:
    """
    Security guardrails for CLI operations.

    Environment-based authentication and read-only mode support.
    """

    def __init__(self) -> None:
        self.auth_token = os.environ.get("INTENTUSNET_AUTH_TOKEN")
        self.mode = self._determine_mode()

    def _determine_mode(self) -> CLIMode:
        """Determine CLI mode from environment."""
        mode_str = os.environ.get("INTENTUSNET_MODE", "read_write")
        if mode_str.lower() in ["readonly", "read_only", "read-only"]:
            return CLIMode.READ_ONLY
        return CLIMode.READ_WRITE

    def check_auth(self) -> bool:
        """
        Check if authentication is valid.

        Returns True if authenticated, False otherwise.
        """
        # If no auth token configured, allow (for local development)
        if not self.auth_token:
            return True

        # Check token from environment
        provided_token = os.environ.get("INTENTUSNET_AUTH_TOKEN")
        return provided_token == self.auth_token

    def guard_write_operation(self, operation_name: str) -> None:
        """
        Guard write operations.

        Raises PermissionError if:
        - Auth check fails
        - CLI is in read-only mode
        """
        if not self.check_auth():
            raise PermissionError(f"Authentication required for {operation_name}")

        if self.mode == CLIMode.READ_ONLY:
            raise PermissionError(f"Operation '{operation_name}' not allowed in read-only mode")

    def confirm_destructive(self, operation_name: str, target: str) -> bool:
        """
        Require confirmation for destructive operations.

        Returns True if confirmed, False otherwise.
        """
        # Check if auto-confirm flag is set (for CI)
        if os.environ.get("INTENTUSNET_AUTO_CONFIRM") == "1":
            return True

        # Interactive confirmation
        print(f"WARNING: Destructive operation '{operation_name}' on '{target}'", file=sys.stderr)
        response = input("Type 'yes' to confirm: ")
        return response.lower() in ["yes", "y"]


def require_auth(func):
    """Decorator to require authentication for CLI commands."""
    def wrapper(*args, **kwargs):
        guard = SecurityGuard()
        if not guard.check_auth():
            print("Error: Authentication required", file=sys.stderr)
            sys.exit(1)
        return func(*args, **kwargs)
    return wrapper


def require_write_mode(func):
    """Decorator to require write mode for CLI commands."""
    def wrapper(*args, **kwargs):
        guard = SecurityGuard()
        try:
            guard.guard_write_operation(func.__name__)
        except PermissionError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return func(*args, **kwargs)
    return wrapper


def require_confirmation(operation_name: str):
    """Decorator to require confirmation for destructive operations."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            guard = SecurityGuard()

            # Determine target from args
            target = "unknown"
            if hasattr(args[0], 'execution_id'):
                target = args[0].execution_id
            elif len(args) > 0 and hasattr(args[0], '__dict__'):
                # Try to extract from args namespace
                for attr in ['execution_id', 'id', 'name']:
                    if hasattr(args[0], attr):
                        target = getattr(args[0], attr)
                        break

            if not guard.confirm_destructive(operation_name, target):
                print("Operation cancelled", file=sys.stderr)
                sys.exit(1)

            return func(*args, **kwargs)
        return wrapper
    return decorator
