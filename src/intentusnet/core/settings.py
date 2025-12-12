"""
Central configuration for IntentusNet.

This module provides a single, typed configuration object that reads from
environment variables (12-factor style) using Pydantic BaseSettings.

Usage:

    from intentusnet.core.settings import get_settings

    settings = get_settings()
    if settings.emcl.enabled:
        ...

You should add `pydantic` to your dependencies:

    pydantic>=1.10
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional, List

from pydantic import BaseSettings, Field, AnyHttpUrl, validator


class EMCLSettings(BaseSettings):
    enabled: bool = Field(
        default=False,
        env="INTENTUSNET_EMCL_ENABLED",
        description="Enable EMCL encryption for transports/gateways.",
    )
    mode: str = Field(
        default="aes-gcm",
        env="INTENTUSNET_EMCL_MODE",
        description="EMCL mode: 'aes-gcm' or 'simple-hmac'.",
    )
    key: str = Field(
        default="",
        env="INTENTUSNET_EMCL_KEY",
        description="Symmetric key / secret for EMCL.",
    )

    class Config:
        env_prefix = ""  # we already used full env names


class JWTSettings(BaseSettings):
    enabled: bool = Field(
        default=False,
        env="INTENTUSNET_JWT_ENABLED",
        description="Enable JWT authentication at gateways.",
    )
    secret: str = Field(
        default="",
        env="INTENTUSNET_JWT_SECRET",
        description="JWT HMAC secret (HS* algorithms).",
    )
    algorithm: str = Field(
        default="HS256",
        env="INTENTUSNET_JWT_ALG",
        description="JWT algorithm (e.g., HS256).",
    )
    issuer: Optional[str] = Field(
        default=None,
        env="INTENTUSNET_JWT_ISSUER",
        description="Expected JWT issuer (optional).",
    )
    audience: Optional[str] = Field(
        default=None,
        env="INTENTUSNET_JWT_AUDIENCE",
        description="Expected JWT audience (optional).",
    )

    @validator("secret")
    def _validate_secret(cls, v: str, values):
        enabled = values.get("enabled", False)
        if enabled and not v:
            raise ValueError("INTENTUSNET_JWT_SECRET is required when JWT is enabled")
        return v

    class Config:
        env_prefix = ""


class PolicySettings(BaseSettings):
    file: Optional[str] = Field(
        default=None,
        env="INTENTUSNET_POLICY_FILE",
        description="Path to JSON/YAML policy file.",
    )
    default_mode: str = Field(
        default="allow",
        env="INTENTUSNET_POLICY_DEFAULT",
        description="'allow' or 'deny' when no rules or file missing.",
    )

    @validator("default_mode")
    def _normalize_default_mode(cls, v: str) -> str:
        v = (v or "allow").lower()
        if v not in ("allow", "deny"):
            return "allow"
        return v

    class Config:
        env_prefix = ""


class GatewaySettings(BaseSettings):
    """
    HTTP gateway-specific settings (host/port, base URL for remote clients, etc.).
    """

    host: str = Field(
        default="0.0.0.0",
        env="INTENTUSNET_HTTP_HOST",
        description="HTTP bind host for FastAPI/Uvicorn gateway.",
    )
    port: int = Field(
        default=8000,
        env="INTENTUSNET_HTTP_PORT",
        description="HTTP bind port for FastAPI/Uvicorn gateway.",
    )
    base_url: Optional[AnyHttpUrl] = Field(
        default=None,
        env="INTENTUSNET_HTTP_BASE_URL",
        description="Public base URL for remote HTTP clients, if exposed.",
    )

    class Config:
        env_prefix = ""


class RuntimeSettings(BaseSettings):
    """
    Core runtime-level settings: concurrency, tracing, etc.
    """

    max_worker_threads: int = Field(
        default=8,
        env="INTENTUSNET_MAX_WORKER_THREADS",
        description="Default thread pool size for blocking agent work.",
    )
    log_level: str = Field(
        default="INFO",
        env="INTENTUSNET_LOG_LEVEL",
        description="Root log level (DEBUG/INFO/WARN/ERROR).",
    )
    trace_sink: str = Field(
        default="memory",
        env="INTENTUSNET_TRACE_SINK",
        description="Trace sink backend: 'memory' (default), 'stdout', 'otel', etc.",
    )

    class Config:
        env_prefix = ""


class IntentusSettings(BaseSettings):
    """
    Root configuration object for IntentusNet.

    Aggregates:
      - EMCL
      - JWT
      - Policy
      - Gateway
      - Runtime
    """

    emcl: EMCLSettings = EMCLSettings()
    jwt: JWTSettings = JWTSettings()
    policy: PolicySettings = PolicySettings()
    gateway: GatewaySettings = GatewaySettings()
    runtime: RuntimeSettings = RuntimeSettings()

    # Optional list of extra middlewares or extensions, reserved for future
    enabled_middlewares: List[str] = Field(
        default_factory=list,
        env="INTENTUSNET_MIDDLEWARES",
        description="Comma-separated list of middleware names to enable.",
    )

    @validator("enabled_middlewares", pre=True)
    def _parse_middlewares(cls, v):
        if isinstance(v, str):
            parts = [x.strip() for x in v.split(",") if x.strip()]
            return parts
        return v

    class Config:
        env_prefix = ""  # we explicitly define env names in inner models


@lru_cache(maxsize=1)
def get_settings() -> IntentusSettings:
    """
    Cached accessor for IntentusSettings.

    Usage:
        from intentusnet.core.settings import get_settings
        settings = get_settings()
    """
    return IntentusSettings()
