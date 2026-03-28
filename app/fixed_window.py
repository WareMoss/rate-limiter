"""Fixed Window rate limiting algorithm."""

import threading
import time
from dataclasses import dataclass, field

from app.base import RateLimiter
from app.exceptions import InvalidConfigError


@dataclass
class _WindowState:
    count: int
    window_start: float = field(default_factory=time.monotonic)


class FixedWindow(RateLimiter):
    """Rate limiter using the Fixed Window algorithm.

    Counts requests within fixed time windows of window_seconds length.
    Simple and predictable, but watch out for burst traffic at window
    boundaries — use TokenBucket if that matters.
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
        self._windows: dict[str, _WindowState] = {}  # O(1) lookup — keyed by caller ID
        self._lock = threading.Lock()

    @property
    def max_requests(self) -> int:
        return self._max_requests

    @property
    def window_seconds(self) -> int:
        return self._window_seconds

    def _get_or_create(self, key: str) -> _WindowState:
        if key not in self._windows:
            self._windows[key] = _WindowState(count=0)
        return self._windows[key]

    def _maybe_reset(self, state: _WindowState) -> None:
        if time.monotonic() - state.window_start >= self._window_seconds:
            state.count = 0
            state.window_start = time.monotonic()

    def allow(self, key: str) -> tuple[bool, int]:
        """Atomically increment and return (allowed, remaining_after)."""
        with self._lock:
            state = self._get_or_create(key)
            self._maybe_reset(state)
            if state.count < self._max_requests:
                state.count += 1
                return True, max(0, self._max_requests - state.count)
            return False, 0

    def remaining(self, key: str) -> int:
        with self._lock:
            if key not in self._windows:
                return self._max_requests
            state = self._windows[key]
            self._maybe_reset(state)
            return max(0, self._max_requests - state.count)

    def window_state(self, key: str) -> tuple[int, float, float]:
        """Return (remaining, elapsed_secs, total_secs) atomically."""
        with self._lock:
            if key not in self._windows:
                return self._max_requests, 0.0, float(self._window_seconds)
            state = self._windows[key]
            self._maybe_reset(state)
            elapsed = time.monotonic() - state.window_start
            remaining = max(0, self._max_requests - state.count)
            return remaining, elapsed, float(self._window_seconds)

    def reset(self, key: str) -> None:
        with self._lock:
            self._windows.pop(key, None)
