"""Abstract base class defining the rate limiter interface."""

from abc import ABC, abstractmethod


class RateLimiter(ABC):
    """
    Abstract base class for all rate limiting strategies.

    All implementations must honour this interface, allowing
    callers to swap strategies without changing their code —
    this is the Open/Closed principle in practice.
    """

    @abstractmethod
    def is_allowed(self, key: str) -> bool:
        """
        Check whether a request from the given key is allowed.

        Args:
            key: A unique identifier for the caller (e.g. user ID, IP address).

        Returns:
            True if the request is within the rate limit, False otherwise.
        """
        ...

    @abstractmethod
    def remaining(self, key: str) -> int:
        """
        Return the number of remaining allowed requests for this key.

        Args:
            key: A unique identifier for the caller.

        Returns:
            Integer count of remaining requests in the current window.
        """
        ...

    @abstractmethod
    def reset(self, key: str) -> None:
        """
        Reset the rate limit state for the given key.

        Args:
            key: A unique identifier for the caller.
        """
        ...
