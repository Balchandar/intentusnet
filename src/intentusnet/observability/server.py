"""
Observability HTTP server.

Provides:
- /health
- /metrics
"""

from __future__ import annotations

import logging
from typing import Optional

from .health import HealthChecker
from .metrics import MetricsCollector

logger = logging.getLogger("intentusnet.observability")


class ObservabilityServer:
    """
    Observability server (FastAPI-based).

    Provides /health and /metrics endpoints.
    """

    def __init__(
        self,
        health_checker: Optional[HealthChecker] = None,
        metrics_collector: Optional[MetricsCollector] = None,
        port: int = 9090,
    ) -> None:
        self.health_checker = health_checker or HealthChecker()
        self.metrics_collector = metrics_collector or MetricsCollector()
        self.port = port
        self._app = None

    def create_app(self):
        """
        Create FastAPI app with health and metrics endpoints.
        """
        try:
            from fastapi import FastAPI
            from fastapi.responses import JSONResponse, PlainTextResponse
        except ImportError:
            logger.warning("FastAPI not installed - observability server disabled")
            return None

        app = FastAPI(title="IntentusNet Observability")

        @app.get("/health")
        async def health():
            result = self.health_checker.check_health()
            return JSONResponse(content=result.to_dict())

        @app.get("/metrics")
        async def metrics():
            metrics_text = self.metrics_collector.get_metrics()
            return PlainTextResponse(content=metrics_text)

        self._app = app
        return app

    def start(self) -> None:
        """
        Start observability server.
        """
        app = self.create_app()
        if app is None:
            logger.warning("Cannot start observability server (FastAPI not available)")
            return

        try:
            import uvicorn
            uvicorn.run(app, host="0.0.0.0", port=self.port, log_level="info")
        except ImportError:
            logger.warning("uvicorn not installed - cannot start observability server")
