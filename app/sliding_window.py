"""Sliding Window rate limiting algorithm."""

import threading
import time
from collections import deque
from dataclasses import dataclass, field

from app.base import RateLimiter
from app.exceptions import InvalidConfigError


@dataclass
class _WindowLog:
    timestamps: deque[float] = field(default_factory=deque)


class SlidingWindow(RateLimiter):
    """Rate limiter using the Sliding Window Log algorithm.

    Tracks per-key request timestamps and counts only those within the last
    window_seconds. Fixes the boundary burst problem Fixed Window has — the
    limit holds across any rolling slice of window_seconds, not just aligned
    buckets. Memory per key is O(max_requests) since old timestamps drop off.
    """

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        if max_requests <= 0:
            raise InvalidConfigError(f"max_requests must be > 0, got {max_requests}")
        if window_seconds <= 0:
            raise InvalidConfigError(
                f"window_seconds must be > 0, got {window_seconds}"
            )

        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._logs: dict[str, _WindowLog] = {}
        self._lock = threading.Lock()

    @property
    def max_requests(self) -> int:
        return self._max_requests

    @property
    def window_seconds(self) -> int:
        return self._window_seconds

    def _get_or_create(self, key: str) -> _WindowLog:
        if key not in self._logs:
            self._logs[key] = _WindowLog()
        return self._logs[key]

    def _prune(self, log: _WindowLog, now: float) -> None:
        cutoff = now - self._window_seconds
        while log.timestamps and log.timestamps[0] <= cutoff:
            log.timestamps.popleft()

    def allow(self, key: str) -> tuple[bool, int]:
        """Atomically record and check. Returns (allowed, remaining_after)."""
        with self._lock:
            now = time.monotonic()
            log = self._get_or_create(key)
            self._prune(log, now)
            if len(log.timestamps) < self._max_requests:
                log.timestamps.append(now)
                return True, self._max_requests - len(log.timestamps)
            return False, 0

    def remaining(self, key: str) -> int:
        with self._lock:
            if key not in self._logs:
                return self._max_requests
            log = self._logs[key]
            self._prune(log, time.monotonic())
            return max(0, self._max_requests - len(log.timestamps))

    def window_state(self, key: str) -> tuple[int, float, float]:
        """Return (remaining, oldest_request_age_secs, window_size_secs)."""
        with self._lock:
            total = float(self._window_seconds)
            if key not in self._logs:
                return self._max_requests, 0.0, total
            log = self._logs[key]
            now = time.monotonic()
            self._prune(log, now)
            remaining = max(0, self._max_requests - len(log.timestamps))
            oldest_age = (now - log.timestamps[0]) if log.timestamps else 0.0
            return remaining, oldest_age, total

    def reset(self, key: str) -> None:
        with self._lock:
            self._logs.pop(key, None)
