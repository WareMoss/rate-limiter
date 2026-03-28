"""Abstract base class for rate limiter implementations."""

from abc import ABC, abstractmethod


class RateLimiter(ABC):
    """Shared interface for rate limiting algorithms.

    Both TokenBucket and FixedWindow implement this contract so they're
    interchangeable wherever a RateLimiter is accepted.
    """

    @abstractmethod
    def allow(self, key: str) -> tuple[bool, int]:
        """Atomically check and consume. Returns (allowed, remaining_after).

        Combining the check and the counter update in one operation means
        the remaining count can't be stale — no race window between them.
        """

    def is_allowed(self, key: str) -> bool:
        """Return True if the request is within the limit."""
        allowed, _ = self.allow(key)
        return allowed

    @abstractmethod
    def remaining(self, key: str) -> int:
        """Remaining quota for key — read-only, does not consume."""

    @abstractmethod
    def reset(self, key: str) -> None:
        """Clear all state for key. Safe to call on unknown keys."""
