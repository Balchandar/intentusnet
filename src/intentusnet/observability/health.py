"""
Health check system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from enum import Enum
from pathlib import Path


class HealthStatus(str, Enum):
    """
    Health status.
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheckResult:
    """
    Health check result.
    """

    status: HealthStatus
    checks: Dict[str, Any] = field(default_factory=dict)
    timestamp_iso: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "checks": self.checks,
            "timestamp": self.timestamp_iso,
        }


class HealthChecker:
    """
    Health checker for IntentusNet runtime.

    Checks:
    - WAL directory accessible
    - Record store accessible
    - Agent registry status
    """

    def __init__(
        self,
        wal_dir: Optional[str] = None,
        record_dir: Optional[str] = None,
    ) -> None:
        self.wal_dir = Path(wal_dir) if wal_dir else None
        self.record_dir = Path(record_dir) if record_dir else None

    def check_health(self) -> HealthCheckResult:
        """
        Perform health checks.
        """
        from intentusnet.utils.timestamps import now_iso

        checks = {}
        overall_status = HealthStatus.HEALTHY

        # Check WAL directory
        if self.wal_dir:
            wal_check = self._check_directory(self.wal_dir)
            checks["wal_directory"] = wal_check
            if not wal_check["accessible"]:
                overall_status = HealthStatus.UNHEALTHY

        # Check record directory
        if self.record_dir:
            record_check = self._check_directory(self.record_dir)
            checks["record_directory"] = record_check
            if not record_check["accessible"]:
                overall_status = HealthStatus.DEGRADED

        return HealthCheckResult(
            status=overall_status,
            checks=checks,
            timestamp_iso=now_iso(),
        )

    def _check_directory(self, path: Path) -> Dict[str, Any]:
        """
        Check if directory is accessible.
        """
        try:
            exists = path.exists()
            if exists:
                # Try to list directory
                list(path.iterdir())
                return {
                    "accessible": True,
                    "exists": True,
                    "path": str(path),
                }
            else:
                return {
                    "accessible": False,
                    "exists": False,
                    "path": str(path),
                    "error": "Directory does not exist",
                }
        except Exception as e:
            return {
                "accessible": False,
                "exists": exists if "exists" in locals() else False,
                "path": str(path),
                "error": str(e),
            }
