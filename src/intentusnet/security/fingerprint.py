"""
Execution Fingerprint Engine

Learns expected execution behavior per intent via a sliding window of
historical samples, then scores deviations as anomalies.

Detects:
  - Latency drift       (z-score vs historical mean)
  - Timeout edge probing (consistently near the observed max latency)
  - Retry manipulation  (retries far above the historical average)
  - Repeated timeouts   (systematic timeout pattern = probing signal)

Output per execution:
  AnomalyResult.anomaly_score  : float 0.0 – 1.0
  AnomalyResult.classification : normal | suspicious | malicious
  AnomalyResult.reasons        : human-readable explanation list
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Dict, List, Optional


class AnomalyClass(str, Enum):
    NORMAL = "normal"
    SUSPICIOUS = "suspicious"
    MALICIOUS = "malicious"


@dataclass
class FingerprintSample:
    latency_ms: float
    retries: int
    timed_out: bool
    timestamp: float = field(default_factory=time.time)


@dataclass
class AnomalyResult:
    anomaly_score: float        # 0.0 – 1.0
    classification: AnomalyClass
    reasons: List[str]


class ExecutionFingerprintEngine:
    """
    Per-intent behavioral anomaly detector.

    Thread-safe. Maintains one sliding window of FingerprintSamples per
    intent name. Scoring uses deterministic statistics (no ML model) so
    results are fully reproducible and auditable.

    Minimum samples before scoring: 5 (returns NORMAL below threshold).
    """

    _MIN_SAMPLES_TO_SCORE = 5

    def __init__(
        self,
        window_size: int = 100,
        anomaly_threshold: float = 0.75,
        malicious_threshold: float = 0.95,
    ) -> None:
        self._window_size = window_size
        self._anomaly_threshold = anomaly_threshold
        self._malicious_threshold = malicious_threshold

        self._samples: Dict[str, Deque[FingerprintSample]] = {}
        self._active_starts: Dict[str, float] = {}   # exec_id → perf_counter start
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Trace lifecycle
    # ------------------------------------------------------------------

    def start_trace(self, execution_id: str) -> None:
        """Record the start of an execution trace."""
        with self._lock:
            self._active_starts[execution_id] = time.perf_counter()

    def end_trace(
        self,
        execution_id: str,
        intent_name: str,
        *,
        retries: int = 0,
        timed_out: bool = False,
    ) -> AnomalyResult:
        """
        Record end of execution, evaluate against historical samples.

        Returns AnomalyResult with score and classification.
        The new sample is appended AFTER scoring (so it never inflates its own score).
        """
        with self._lock:
            start = self._active_starts.pop(execution_id, None)
            latency_ms = (time.perf_counter() - start) * 1000.0 if start is not None else 0.0

            sample = FingerprintSample(
                latency_ms=latency_ms,
                retries=retries,
                timed_out=timed_out,
            )

            if intent_name not in self._samples:
                self._samples[intent_name] = deque(maxlen=self._window_size)

            history = self._samples[intent_name]
            result = self._evaluate(sample, history)

            # Append after evaluation — new sample must not bias its own score
            history.append(sample)

        return result

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _evaluate(
        self,
        sample: FingerprintSample,
        history: Deque[FingerprintSample],
    ) -> AnomalyResult:
        if len(history) < self._MIN_SAMPLES_TO_SCORE:
            return AnomalyResult(0.0, AnomalyClass.NORMAL, [])

        reasons: List[str] = []
        score = 0.0

        latencies = [s.latency_ms for s in history]
        mean_lat = sum(latencies) / len(latencies)
        variance = sum((x - mean_lat) ** 2 for x in latencies) / len(latencies)
        std_dev = variance ** 0.5

        # 1. Latency drift — z-score beyond 4σ signals something unusual
        if std_dev > 0.0:
            z = abs(sample.latency_ms - mean_lat) / std_dev
            if z > 4.0:
                drift = min(1.0, (z - 4.0) / 4.0)
                score = max(score, drift)
                reasons.append(
                    f"latency_drift z={z:.2f} "
                    f"(sample={sample.latency_ms:.1f}ms mean={mean_lat:.1f}ms σ={std_dev:.1f}ms)"
                )

        # 2. Timeout edge probing — repeatedly hitting near max observed latency.
        # Only meaningful when there IS variance in the historical data.
        # If std_dev == 0 all executions have identical latency — that is normal.
        recent = list(history)[-10:]
        if len(recent) >= 5 and std_dev > 0.0:
            max_recent = max(s.latency_ms for s in recent)
            if max_recent > 0.0:
                proximity = sample.latency_ms / max_recent
                if proximity > 0.92:
                    # Scale 0.92 → 0.0, 1.0 → 1.0 (capped at 0.8 weight)
                    edge = min(1.0, (proximity - 0.92) / 0.08) * 0.8
                    score = max(score, edge)
                    reasons.append(
                        f"timeout_edge_probing proximity={proximity:.1%} of max={max_recent:.1f}ms"
                    )

        # 3. Retry manipulation — retries far above historical average
        if sample.retries > 0:
            avg_retries = sum(s.retries for s in history) / len(history)
            threshold = avg_retries * 3.0 + 2.0
            if sample.retries > threshold:
                retry_score = min(1.0, (sample.retries - threshold) / 10.0) * 0.7
                score = max(score, retry_score)
                reasons.append(
                    f"retry_anomaly retries={sample.retries} avg={avg_retries:.1f} threshold={threshold:.1f}"
                )

        # 4. Repeated timeouts — systematic pattern = probing/DoS signal
        if sample.timed_out:
            last_20 = list(history)[-20:]
            recent_timeouts = sum(1 for s in last_20 if s.timed_out)
            if recent_timeouts >= 3:
                to_score = min(1.0, recent_timeouts / 10.0)
                score = max(score, to_score)
                reasons.append(
                    f"repeated_timeouts count={recent_timeouts} in last {len(last_20)} samples"
                )

        score = min(1.0, score)

        if score >= self._malicious_threshold:
            cls = AnomalyClass.MALICIOUS
        elif score >= self._anomaly_threshold:
            cls = AnomalyClass.SUSPICIOUS
        else:
            cls = AnomalyClass.NORMAL

        return AnomalyResult(score, cls, reasons)

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def get_profile(self, intent_name: str) -> Optional[Dict]:
        """Return the current learned profile for an intent (for dashboards)."""
        with self._lock:
            history = self._samples.get(intent_name)
            if not history or len(history) < 2:
                return None
            latencies = [s.latency_ms for s in history]
            mean = sum(latencies) / len(latencies)
            return {
                "intent": intent_name,
                "sample_count": len(history),
                "mean_latency_ms": round(mean, 2),
                "min_latency_ms": round(min(latencies), 2),
                "max_latency_ms": round(max(latencies), 2),
                "total_timeouts": sum(1 for s in history if s.timed_out),
                "total_retried": sum(1 for s in history if s.retries > 0),
            }

    def known_intents(self) -> List[str]:
        with self._lock:
            return list(self._samples.keys())

    def reset_intent(self, intent_name: str) -> None:
        """Clear the sample window for an intent (e.g. after a deployment)."""
        with self._lock:
            self._samples.pop(intent_name, None)
