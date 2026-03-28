"""Custom exceptions for the rate limiter library."""


class InvalidConfigError(ValueError):
    """Raised for invalid constructor arguments (zero/negative capacity, etc.)."""


class RateLimitExceededError(Exception):
    """Raised instead of returning False when strict mode is enabled."""
