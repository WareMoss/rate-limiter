"""Custom exceptions for the rate limiter library."""


class InvalidConfigError(ValueError):
    """Raised when a rate limiter is configured with invalid parameters."""
    pass


class RateLimitExceededError(Exception):
    """Raised when a rate limit is exceeded (optional strict mode)."""
    pass
