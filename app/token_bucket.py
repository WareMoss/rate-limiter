"""
Token Bucket rate limiting algorithm.

Each key gets a bucket that holds up to `capacity` tokens.
Tokens are consumed on each request and refill at `refill_rate`
tokens per second. Requests are blocked when the bucket is empty.

Time complexity:  O(1) per operation
Space complexity: O(n) where n is the number of unique keys
"""

import time
from dataclasses import dataclass, field

from app.base import RateLimiter
from app.exceptions import InvalidConfigError


@dataclass
class _BucketState:
    """Internal state for a single key's token bucket."""

    tokens: float
    last_refill: float = field(default_factory=time.monotonic)


class TokenBucket(RateLimiter):
    """
    Rate limiter using the Token Bucket algorithm.

    Args:
        capacity:    Maximum number of tokens the bucket can hold.
        refill_rate: Number of tokens added per second.

    Raises:
        InvalidConfigError: If capacity <= 0 or refill_rate < 0.
    """

    def __init__(self, capacity: int, refill_rate: float) -> None:
        if capacity <= 0:
            raise InvalidConfigError("capacity must be greater than 0")
        if refill_rate < 0:
            raise InvalidConfigError("refill_rate must be >= 0")

        self._capacity = capacity
        self._refill_rate = refill_rate
        # O(1) lookup keyed by caller identifier
        self._buckets: dict[str, _BucketState] = {}

    def _get_bucket(self, key: str) -> _BucketState:
        """Retrieve or initialise a bucket for the given key."""
        if key not in self._buckets:
            self._buckets[key] = _BucketState(tokens=float(self._capacity))
        return self._buckets[key]

    def _refill(self, bucket: _BucketState) -> None:
        """Add tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - bucket.last_refill
        new_tokens = elapsed * self._refill_rate
        bucket.tokens = min(self._capacity, bucket.tokens + new_tokens)
        bucket.last_refill = now

    def is_allowed(self, key: str) -> bool:
        """Return True and consume a token if the bucket is non-empty."""
        bucket = self._get_bucket(key)
        self._refill(bucket)

        if bucket.tokens >= 1:
            bucket.tokens -= 1
            return True
        return False

    def remaining(self, key: str) -> int:
        """Return the number of whole tokens remaining in the bucket."""
        bucket = self._get_bucket(key)
        self._refill(bucket)
        return int(bucket.tokens)

    def reset(self, key: str) -> None:
        """Reset the bucket for the given key to full capacity."""
        self._buckets[key] = _BucketState(tokens=float(self._capacity))
