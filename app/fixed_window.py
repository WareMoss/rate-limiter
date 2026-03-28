"""Fixed Window rate limiting algorithm.

Divides time into fixed-length windows. Each window allows up to
*max_requests* requests. When the window expires the counter resets.
Simple to implement and reason about; susceptible to burst traffic at
window boundaries (use Token Bucket when smoothness matters more).

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
class _WindowState:
    """Per-key mutable state for a single fixed window."""

    count: int
    window_start: float = field(default_factory=time.monotonic)


class FixedWindow(RateLimiter):
    """Rate limiter using the Fixed Window algorithm.

    Counts requests within a fixed time window of *window_seconds* seconds.
    Once *max_requests* is reached all further requests in the same window are
    denied. The counter resets when a new window begins.

    Args:
        max_requests: Maximum requests allowed per window. Must be > 0.
        window_seconds: Window length in seconds. Must be > 0.

    Raises:
        InvalidConfigError: If *max_requests* <= 0 or *window_seconds* <= 0.
    """

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        """Initialise the limiter and validate configuration."""
        if max_requests <= 0:
            raise InvalidConfigError(
                f"max_requests must be a positive integer, got {max_requests}"
            )
        if window_seconds <= 0:
            raise InvalidConfigError(
                f"window_seconds must be a positive integer, got {window_seconds}"
            )
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        # O(1) lookup — dict keyed by caller identifier
        self._windows: dict[str, _WindowState] = {}
        # Single lock guards the entire dict — serialises concurrent access so
        # no two threads can observe or mutate the same window simultaneously.
        self._lock = threading.Lock()

    @property
    def max_requests(self) -> int:
        """Maximum requests per window (immutable after construction)."""
        return self._max_requests

    @property
    def window_seconds(self) -> int:
        """Window duration in seconds (immutable after construction)."""
        return self._window_seconds

    # ── Internal helpers (must be called while holding self._lock) ────────────

    def _get_or_create(self, key: str) -> _WindowState:
        """Return existing window state for *key*, creating it if absent."""
        if key not in self._windows:
            self._windows[key] = _WindowState(count=0)
        return self._windows[key]

    def _maybe_reset_window(self, state: _WindowState) -> None:
        """Reset the counter if the current window has expired."""
        now = time.monotonic()
        if now - state.window_start >= self._window_seconds:
            state.count = 0
            state.window_start = now

    # ── Public interface ──────────────────────────────────────────────────────

    def allow(self, key: str) -> tuple[bool, int]:
        """Atomically increment the counter and return (allowed, remaining_after).

        The window expiry check, counter increment, and remaining calculation
        all happen inside the same lock acquisition so the returned remaining
        count is consistent with the allow/deny decision.

        Args:
            key: Caller identifier.

        Returns:
            ``(True, remaining)`` if the request is within the window limit,
            ``(False, 0)`` if the limit has been reached.
        """
        with self._lock:
            state = self._get_or_create(key)
            self._maybe_reset_window(state)
            if state.count < self._max_requests:
                state.count += 1
                return True, max(0, self._max_requests - state.count)
            return False, 0

    def remaining(self, key: str) -> int:
        """Return the number of requests still allowed in the current window.

        For a key that has never been seen this returns *max_requests* without
        creating any internal state — purely a read-only fast path.

        Args:
            key: Caller identifier.

        Returns:
            Integer in [0, max_requests].
        """
        with self._lock:
            if key not in self._windows:
                # Unknown key — window would be fresh, no state to create.
                return self._max_requests
            state = self._windows[key]
            self._maybe_reset_window(state)
            return max(0, self._max_requests - state.count)

    def window_state(self, key: str) -> tuple[int, float, float]:
        """Return (remaining, elapsed_seconds, window_total_seconds) atomically.

        All three values are derived inside a single lock acquisition so they
        are mutually consistent — the dashboard can safely display remaining
        alongside a countdown without the two figures being from different
        window epochs.

        Args:
            key: Caller identifier.

        Returns:
            A tuple ``(remaining, elapsed, total)`` where *elapsed* is how many
            seconds have passed in the current window and *total* is
            ``window_seconds``.
        """
        with self._lock:
            if key not in self._windows:
                return self._max_requests, 0.0, float(self._window_seconds)
            state = self._windows[key]
            self._maybe_reset_window(state)
            elapsed = time.monotonic() - state.window_start
            remaining = max(0, self._max_requests - state.count)
            return remaining, elapsed, float(self._window_seconds)

    def reset(self, key: str) -> None:
        """Remove all state for *key*, as if it has never made a request.

        Safe to call for keys that have never been seen.

        Args:
            key: Caller identifier to clear.
        """
        with self._lock:
            self._windows.pop(key, None)
