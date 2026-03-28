"""Custom exceptions for the rate limiter library."""


class InvalidConfigError(ValueError):
    """Raised when a rate limiter is constructed with invalid parameters.

    Examples of invalid configuration: zero or negative capacity,
    negative refill rate, zero window duration.
    """


class RateLimitExceededError(Exception):
    """Raised when a request is rejected in strict mode.

    In strict mode callers receive this exception instead of a False
    return value so they can handle throttling at the call site.
    """
