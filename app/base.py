"""Abstract base class defining the polymorphic rate limiter interface."""

from abc import ABC, abstractmethod


class RateLimiter(ABC):
    """Common interface for all rate limiting algorithm implementations.

    Any concrete implementation (TokenBucket, FixedWindow, etc.) must
    satisfy this contract, making algorithms interchangeable wherever a
    RateLimiter is accepted.

    Design notes:
    - ``allow()`` is the primary abstract method — it is atomic (check + consume
      happen under the same lock) so the returned remaining count can never be
      stale relative to the allow/deny decision.
    - ``is_allowed()`` is a convenience wrapper provided here on the base class;
      concrete classes do not need to override it.
    """

    @abstractmethod
    def allow(self, key: str) -> tuple[bool, int]:
        """Atomically check, consume, and return (allowed, remaining).

        Combining the check and the counter update in a single operation
        eliminates the race condition that arises when ``is_allowed()`` and
        ``remaining()`` are called separately — another thread cannot sneak in
        between the two calls and make the remaining count stale.

        Args:
            key: An arbitrary string identifying the caller (IP, user ID, …).

        Returns:
            A tuple ``(allowed, remaining_after)`` where *remaining_after* is
            the quota left *after* this request has been processed.
        """

    def is_allowed(self, key: str) -> bool:
        """Return True if the request identified by *key* is within the limit.

        Delegates to :meth:`allow` so is_allowed() is always consistent with
        the remaining count returned by that call.

        Args:
            key: The caller identifier.

        Returns:
            True if the request is permitted, False if it is throttled.
        """
        allowed, _ = self.allow(key)
        return allowed

    @abstractmethod
    def remaining(self, key: str) -> int:
        """Return the remaining allowed requests for *key* (read-only).

        Does not consume a token or increment a counter.  For an atomic
        check-and-consume use :meth:`allow` instead.

        Args:
            key: The caller identifier.

        Returns:
            Non-negative integer representing remaining capacity.
        """

    @abstractmethod
    def reset(self, key: str) -> None:
        """Reset all rate-limiting state for *key*.

        After this call the key is treated as if it has never been seen.
        Calling reset on an unknown key must not raise.

        Args:
            key: The caller identifier to clear.
        """
