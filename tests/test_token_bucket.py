"""
Unit tests for TokenBucket rate limiter.
All tests written BEFORE implementation — TDD red phase.
"""

import time

import pytest

from app.exceptions import InvalidConfigError
from app.token_bucket import TokenBucket


class TestTokenBucketAllowance:
    """Tests for core allow/block behaviour."""

    def test_allows_first_request(self) -> None:
        limiter = TokenBucket(capacity=5, refill_rate=1.0)
        assert limiter.is_allowed("user_1") is True

    def test_blocks_when_capacity_exhausted(self) -> None:
        limiter = TokenBucket(capacity=1, refill_rate=0.0)
        limiter.is_allowed("user_1")
        assert limiter.is_allowed("user_1") is False

    def test_different_keys_are_independent(self) -> None:
        limiter = TokenBucket(capacity=1, refill_rate=0.0)
        limiter.is_allowed("user_1")
        assert limiter.is_allowed("user_2") is True

    def test_remaining_decrements_on_consume(self) -> None:
        limiter = TokenBucket(capacity=3, refill_rate=0.0)
        limiter.is_allowed("user_1")
        assert limiter.remaining("user_1") == 2

    def test_remaining_never_goes_below_zero(self) -> None:
        limiter = TokenBucket(capacity=1, refill_rate=0.0)
        limiter.is_allowed("user_1")
        limiter.is_allowed("user_1")
        assert limiter.remaining("user_1") == 0


class TestTokenBucketReset:
    """Tests for reset behaviour."""

    def test_reset_restores_full_capacity(self) -> None:
        limiter = TokenBucket(capacity=2, refill_rate=0.0)
        limiter.is_allowed("user_1")
        limiter.reset("user_1")
        assert limiter.remaining("user_1") == 2

    def test_reset_unknown_key_does_not_raise(self) -> None:
        limiter = TokenBucket(capacity=2, refill_rate=0.0)
        limiter.reset("ghost_user")


class TestTokenBucketRefill:
    """Tests for token refill over time."""

    def test_tokens_refill_after_wait(self) -> None:
        limiter = TokenBucket(capacity=2, refill_rate=2.0)
        limiter.is_allowed("user_1")
        limiter.is_allowed("user_1")
        assert limiter.remaining("user_1") == 0
        time.sleep(1.1)
        assert limiter.remaining("user_1") >= 1

    def test_refill_does_not_exceed_capacity(self) -> None:
        limiter = TokenBucket(capacity=3, refill_rate=10.0)
        time.sleep(1.0)
        assert limiter.remaining("user_1") <= 3


class TestTokenBucketValidation:
    """Tests for invalid configuration."""

    def test_raises_on_zero_capacity(self) -> None:
        with pytest.raises(InvalidConfigError):
            TokenBucket(capacity=0, refill_rate=1.0)

    def test_raises_on_negative_capacity(self) -> None:
        with pytest.raises(InvalidConfigError):
            TokenBucket(capacity=-1, refill_rate=1.0)

    def test_raises_on_negative_refill_rate(self) -> None:
        with pytest.raises(InvalidConfigError):
            TokenBucket(capacity=5, refill_rate=-1.0)
