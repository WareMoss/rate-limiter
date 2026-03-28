"""Tests for the TokenBucket rate limiter implementation."""

import time

import pytest

from app.exceptions import InvalidConfigError
from app.token_bucket import TokenBucket


class TestTokenBucketAllowance:
    """Tests for basic allow/deny behaviour."""

    def test_allows_first_request(self) -> None:
        """A fresh bucket with capacity >= 1 must allow the first request."""
        limiter = TokenBucket(capacity=5, refill_rate=1.0)
        assert limiter.is_allowed("user_1") is True

    def test_blocks_when_capacity_exhausted(self) -> None:
        """With refill_rate=0, a second request on a capacity=1 bucket is denied."""
        limiter = TokenBucket(capacity=1, refill_rate=0.0)
        assert limiter.is_allowed("user_1") is True
        assert limiter.is_allowed("user_1") is False

    def test_different_keys_are_independent(self) -> None:
        """Exhausting one key must not affect a different key's bucket."""
        limiter = TokenBucket(capacity=1, refill_rate=0.0)
        limiter.is_allowed("user_1")  # exhaust user_1
        assert limiter.is_allowed("user_2") is True

    def test_remaining_decrements_on_consume(self) -> None:
        """remaining() must reflect tokens consumed by is_allowed()."""
        limiter = TokenBucket(capacity=3, refill_rate=0.0)
        limiter.is_allowed("user_1")
        assert limiter.remaining("user_1") == 2

    def test_remaining_never_goes_below_zero(self) -> None:
        """remaining() must return 0, not a negative number, when exhausted."""
        limiter = TokenBucket(capacity=1, refill_rate=0.0)
        limiter.is_allowed("user_1")
        limiter.is_allowed("user_1")  # attempt beyond capacity
        assert limiter.remaining("user_1") == 0


class TestTokenBucketReset:
    """Tests for the reset() method."""

    def test_reset_restores_full_capacity(self) -> None:
        """After consuming tokens and calling reset, remaining == capacity."""
        capacity = 4
        limiter = TokenBucket(capacity=capacity, refill_rate=0.0)
        limiter.is_allowed("user_1")
        limiter.is_allowed("user_1")
        limiter.reset("user_1")
        assert limiter.remaining("user_1") == capacity

    def test_reset_unknown_key_does_not_raise(self) -> None:
        """reset() on a key that was never seen must not raise any exception."""
        limiter = TokenBucket(capacity=5, refill_rate=1.0)
        limiter.reset("never_seen")  # must not raise


class TestTokenBucketRefill:
    """Tests for token refill behaviour over time."""

    def test_tokens_refill_after_wait(self) -> None:
        """After exhausting the bucket and sleeping, tokens must have refilled."""
        limiter = TokenBucket(capacity=2, refill_rate=2.0)
        # exhaust the bucket
        limiter.is_allowed("user_1")
        limiter.is_allowed("user_1")
        assert limiter.remaining("user_1") == 0

        time.sleep(1.1)  # 1.1 s * 2 tokens/s = 2.2 tokens earned

        assert limiter.remaining("user_1") >= 1

    def test_refill_does_not_exceed_capacity(self) -> None:
        """No matter how long we wait, remaining() must never exceed capacity."""
        capacity = 3
        limiter = TokenBucket(capacity=capacity, refill_rate=10.0)
        time.sleep(1.0)  # would produce 10 tokens if uncapped
        assert limiter.remaining("user_1") <= capacity


class TestTokenBucketValidation:
    """Tests for constructor validation."""

    def test_raises_on_zero_capacity(self) -> None:
        """capacity=0 must raise InvalidConfigError."""
        with pytest.raises(InvalidConfigError):
            TokenBucket(capacity=0, refill_rate=1.0)

    def test_raises_on_negative_capacity(self) -> None:
        """capacity=-1 must raise InvalidConfigError."""
        with pytest.raises(InvalidConfigError):
            TokenBucket(capacity=-1, refill_rate=1.0)

    def test_raises_on_negative_refill_rate(self) -> None:
        """refill_rate=-0.5 must raise InvalidConfigError."""
        with pytest.raises(InvalidConfigError):
            TokenBucket(capacity=5, refill_rate=-0.5)


class TestTokenBucketProperties:
    """Tests for public properties."""

    def test_capacity_property(self) -> None:
        """capacity property must reflect the constructor argument."""
        limiter = TokenBucket(capacity=7, refill_rate=1.0)
        assert limiter.capacity == 7


class TestTokenBucketAllow:
    """Tests for the atomic allow() method."""

    def test_allow_returns_tuple(self) -> None:
        """allow() must return a (bool, int) tuple."""
        limiter = TokenBucket(capacity=3, refill_rate=0.0)
        result = limiter.allow("user_1")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_allow_returns_remaining_after_consume(self) -> None:
        """remaining in the tuple must reflect the count after this request."""
        limiter = TokenBucket(capacity=3, refill_rate=0.0)
        allowed, remaining = limiter.allow("user_1")
        assert allowed is True
        assert remaining == 2  # capacity=3, one consumed → 2 left

    def test_allow_denied_remaining_is_zero(self) -> None:
        """When the bucket is empty the returned remaining must be 0."""
        limiter = TokenBucket(capacity=1, refill_rate=0.0)
        limiter.allow("user_1")  # consume the only token
        allowed, remaining = limiter.allow("user_1")
        assert allowed is False
        assert remaining == 0
