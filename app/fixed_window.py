"""
Fixed Window Counter rate limiting algorithm.

Each key is allowed up to `max_requests` requests within a
fixed time window of `window_seconds`. The counter resets
at the start of each new window.

Time complexity:  O(1) per operation
Space complexity: O(n) where n is the number of unique keys
"""

import time
from dataclasses import dataclass, field

from app.base import RateLimiter
from app.exceptions import InvalidConfigError


@dataclass
class _WindowState:
    """Internal state for a single key's fixed window."""

    count: int = 0
    window_start: float = field(default_factory=time.monotonic)


class FixedWindow(RateLimiter):
    """
    Rate limiter using the Fixed Window Counter algorithm.

    Args:
        max_requests:   Maximum requests allowed per window.
        window_seconds: Duration of each window in seconds.

    Raises:
        InvalidConfigError: If max_requests <= 0 or window_seconds <= 0.
    """

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        if max_requests <= 0:
            raise InvalidConfigError("max_requests must be greater than 0")
        if window_seconds <= 0:
            raise InvalidConfigError("window_seconds must be greater than 0")

        self._max_requests = max_requests
        self._window_seconds = window_seconds
        # O(1) lookup keyed by caller identifier
        self._windows: dict[str, _WindowState] = {}

    def _get_window(self, key: str) -> _WindowState:
        """Retrieve or initialise a window state for the given key."""
        if key not in self._windows:
            self._windows[key] = _WindowState()
        return self._windows[key]

    def _reset_if_expired(self, window: _WindowState) -> None:
        """Reset the window counter if the current window has expired."""
        now = time.monotonic()
        if now - window.window_start >= self._window_seconds:
            window.count = 0
            window.window_start = now

    def is_allowed(self, key: str) -> bool:
        """Return True and increment counter if within the window limit."""
        window = self._get_window(key)
        self._reset_if_expired(window)

        if window.count < self._max_requests:
            window.count += 1
            return True
        return False

    def remaining(self, key: str) -> int:
        """Return the number of remaining requests in the current window."""
        window = self._get_window(key)
        self._reset_if_expired(window)
        return max(0, self._max_requests - window.count)

    def reset(self, key: str) -> None:
        """Reset the window state for the given key."""
        self._windows[key] = _WindowState()
