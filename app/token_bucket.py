"""Token Bucket rate limiting algorithm.

Tokens accumulate at a fixed rate up to a maximum capacity. Each allowed
request consumes one token. When the bucket is empty requests are denied.
This naturally handles burst traffic up to *capacity* and sustains throughput
at *refill_rate* requests per second.

Thread safety: a single ``threading.Lock`` guards all mutations so this class
is safe to share across threads (e.g. multiple uvicorn workers or async tasks
dispatched to a thread pool).
"""

import threading
import time
from dataclasses import dataclass, field

from app.base import RateLimiter
from app.exceptions import InvalidConfigError


@dataclass
class _BucketState:
    """Per-key mutable state for a single token bucket."""

    tokens: float
    last_refill: float = field(default_factory=time.monotonic)


class TokenBucket(RateLimiter):
    """Rate limiter using the Token Bucket algorithm.

    Tokens are added to the bucket at *refill_rate* tokens per second up to
    *capacity*. Each call to :meth:`allow` that succeeds consumes one token.
    When the bucket is empty the request is denied.

    Args:
        capacity: Maximum number of tokens the bucket can hold. Must be > 0.
        refill_rate: Tokens added per second. Must be >= 0. A rate of 0
                     means the bucket never refills after the initial fill.

    Raises:
        InvalidConfigError: If *capacity* <= 0 or *refill_rate* < 0.
    """

    def __init__(self, capacity: int, refill_rate: float) -> None:
        """Initialise the limiter and validate configuration."""
        if capacity <= 0:
            raise InvalidConfigError(
                f"capacity must be a positive integer, got {capacity}"
            )
        if refill_rate < 0:
            raise InvalidConfigError(
                f"refill_rate must be >= 0, got {refill_rate}"
            )
        self._capacity = capacity
        self._refill_rate = refill_rate
        # O(1) lookup — dict keyed by caller identifier
        self._buckets: dict[str, _BucketState] = {}
        # Single lock guards the entire dict — serialises concurrent access so
        # no two threads can observe or mutate the same bucket simultaneously.
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        """Maximum token capacity (immutable after construction)."""
        return self._capacity

    # ── Internal helpers (must be called while holding self._lock) ────────────

    def _get_or_create(self, key: str) -> _BucketState:
        """Return existing bucket state for *key*, creating it if absent."""
        if key not in self._buckets:
            self._buckets[key] = _BucketState(tokens=float(self._capacity))
        return self._buckets[key]

    def _refill(self, state: _BucketState) -> None:
        """Add tokens earned since the last refill, capped at capacity.

        Using time.monotonic() avoids problems with system clock adjustments
        (DST, NTP corrections, etc.) that would break elapsed-time arithmetic.
        """
        now = time.monotonic()
        elapsed = now - state.last_refill
        earned = elapsed * self._refill_rate
        state.tokens = min(float(self._capacity), state.tokens + earned)
        state.last_refill = now

    # ── Public interface ──────────────────────────────────────────────────────

    def allow(self, key: str) -> tuple[bool, int]:
        """Atomically consume one token and return (allowed, remaining_after).

        The check and the token deduction happen inside the same lock
        acquisition, so the remaining count in the return value always
        reflects the state *after* this specific request — no race window.

        Args:
            key: Caller identifier.

        Returns:
            ``(True, remaining)`` if a token was available and consumed,
            ``(False, 0)`` if the bucket was empty.
        """
        with self._lock:
            state = self._get_or_create(key)
            self._refill(state)
            if state.tokens >= 1.0:
                state.tokens -= 1.0
                return True, int(state.tokens)
            return False, int(state.tokens)

    def remaining(self, key: str) -> int:
        """Return the number of whole tokens currently in the bucket.

        Performs a refill calculation so the value reflects tokens that have
        accumulated since the last request.  Does not consume any tokens.

        For a key that has never been seen this returns *capacity* without
        creating any internal state — purely a read-only fast path.

        Args:
            key: Caller identifier.

        Returns:
            Integer token count in [0, capacity].
        """
        with self._lock:
            if key not in self._buckets:
                # Unknown key — bucket would be full, no state to create.
                return self._capacity
            state = self._buckets[key]
            self._refill(state)
            return int(state.tokens)

    def reset(self, key: str) -> None:
        """Remove all state for *key*, restoring it to a full bucket.

        Safe to call for keys that have never been seen.

        Args:
            key: Caller identifier to clear.
        """
        with self._lock:
            self._buckets.pop(key, None)
