from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class RateLimiter:
    """
    Simple in-memory token bucket rate limiter.

    - Per key (e.g., "tenant:intent")
    - rate_per_minute: allowed events per minute
    """

    def __init__(self) -> None:
        self._buckets: Dict[str, _Bucket] = {}

    def check_and_consume(self, key: str, rate_per_minute: int) -> bool:
        """
        Returns True if the request is allowed and consumes a token.
        Returns False if rate limit exceeded.
        """
        if rate_per_minute <= 0:
            return False

        now = time.time()
        bucket = self._buckets.get(key)

        if bucket is None:
            bucket = _Bucket(tokens=float(rate_per_minute), last_refill=now)
            self._buckets[key] = bucket

        # Refill tokens based on elapsed time
        elapsed = now - bucket.last_refill
        refill_rate_per_sec = rate_per_minute / 60.0
        bucket.tokens = min(
            float(rate_per_minute),
            bucket.tokens + elapsed * refill_rate_per_sec,
        )
        bucket.last_refill = now

        if bucket.tokens < 1.0:
            # Not enough tokens
            return False

        bucket.tokens -= 1.0
        return True
