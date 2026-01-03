"""
Metrics collection (Prometheus-compatible).
"""

from __future__ import annotations

import threading
from typing import Dict, Optional
from enum import Enum
from collections import defaultdict


class MetricType(str, Enum):
    """
    Metric types (Prometheus-compatible).
    """

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


class MetricsCollector:
    """
    Prometheus-compatible metrics collector.

    Thread-safe.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, list[float]] = defaultdict(list)

    def increment_counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """
        Increment a counter.
        """
        key = self._make_key(name, labels)
        with self._lock:
            self._counters[key] += value

    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """
        Set a gauge value.
        """
        key = self._make_key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def observe_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """
        Observe a histogram value.
        """
        key = self._make_key(name, labels)
        with self._lock:
            self._histograms[key].append(value)

    def get_metrics(self) -> str:
        """
        Get metrics in Prometheus text format.
        """
        lines = []

        with self._lock:
            # Counters
            for key, value in self._counters.items():
                lines.append(f"# TYPE {key} counter")
                lines.append(f"{key} {value}")

            # Gauges
            for key, value in self._gauges.items():
                lines.append(f"# TYPE {key} gauge")
                lines.append(f"{key} {value}")

            # Histograms (simplified - just count and sum)
            for key, values in self._histograms.items():
                count = len(values)
                total = sum(values)
                lines.append(f"# TYPE {key} histogram")
                lines.append(f"{key}_count {count}")
                lines.append(f"{key}_sum {total}")

        return "\n".join(lines) + "\n"

    def _make_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """
        Make metric key with labels.
        """
        if not labels:
            return name

        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def reset(self) -> None:
        """
        Reset all metrics.
        """
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
