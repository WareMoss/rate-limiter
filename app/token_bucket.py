"""Token Bucket rate limiting algorithm."""

import threading
import time
from dataclasses import dataclass, field

from app.base import RateLimiter
from app.exceptions import InvalidConfigError


@dataclass
class _BucketState:
    tokens: float
    last_refill: float = field(default_factory=time.monotonic)


class TokenBucket(RateLimiter):
    """Rate limiter using the Token Bucket algorithm.

    Tokens refill at refill_rate/sec up to capacity. Each allowed request
    consumes one token. Good for allowing short bursts while enforcing a
    sustained average rate.
    """

    def __init__(self, capacity: int, refill_rate: float) -> None:
        if capacity <= 0:
            raise InvalidConfigError(f"capacity must be > 0, got {capacity}")
        if refill_rate < 0:
            raise InvalidConfigError(f"refill_rate must be >= 0, got {refill_rate}")

        self._capacity = capacity
        self._refill_rate = refill_rate
        self._buckets: dict[str, _BucketState] = {}  # O(1) lookup — keyed by caller ID
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    def _get_or_create(self, key: str) -> _BucketState:
        if key not in self._buckets:
            self._buckets[key] = _BucketState(tokens=float(self._capacity))
        return self._buckets[key]

    def _refill(self, state: _BucketState) -> None:
        # monotonic avoids problems with NTP/DST clock adjustments
        now = time.monotonic()
        elapsed = now - state.last_refill
        earned = elapsed * self._refill_rate
        state.tokens = min(float(self._capacity), state.tokens + earned)
        state.last_refill = now

    def allow(self, key: str) -> tuple[bool, int]:
        """Atomically consume one token. Returns (allowed, remaining_after)."""
        with self._lock:
            state = self._get_or_create(key)
            self._refill(state)
            if state.tokens >= 1.0:
                state.tokens -= 1.0
                return True, int(state.tokens)
            return False, int(state.tokens)

    def remaining(self, key: str) -> int:
        with self._lock:
            if key not in self._buckets:
                return self._capacity
            state = self._buckets[key]
            self._refill(state)
            return int(state.tokens)

    def reset(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)
