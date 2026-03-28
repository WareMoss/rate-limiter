"""Tests for the FixedWindow rate limiter implementation."""

import time

import pytest

from app.exceptions import InvalidConfigError
from app.fixed_window import FixedWindow


class TestFixedWindowAllowance:
    """Tests for basic allow/deny behaviour."""

    def test_allows_first_request(self) -> None:
        """A fresh window must allow the first request."""
        limiter = FixedWindow(max_requests=5, window_seconds=60)
        assert limiter.is_allowed("user_1") is True

    def test_blocks_when_limit_reached(self) -> None:
        """The third request on a max=2 window must be denied."""
        limiter = FixedWindow(max_requests=2, window_seconds=60)
        assert limiter.is_allowed("user_1") is True
        assert limiter.is_allowed("user_1") is True
        assert limiter.is_allowed("user_1") is False

    def test_different_keys_are_independent(self) -> None:
        """Exhausting one key must not affect a different key's window."""
        limiter = FixedWindow(max_requests=1, window_seconds=60)
        limiter.is_allowed("user_1")  # exhaust user_1
        assert limiter.is_allowed("user_2") is True

    def test_remaining_decrements_correctly(self) -> None:
        """remaining() must decrease by 1 for each allowed request."""
        limiter = FixedWindow(max_requests=4, window_seconds=60)
        limiter.is_allowed("user_1")
        limiter.is_allowed("user_1")
        assert limiter.remaining("user_1") == 2


class TestFixedWindowReset:
    """Tests for the reset() method."""

    def test_reset_restores_full_allowance(self) -> None:
        """After consuming requests and calling reset, remaining == max_requests."""
        max_requests = 3
        limiter = FixedWindow(max_requests=max_requests, window_seconds=60)
        limiter.is_allowed("user_1")
        limiter.is_allowed("user_1")
        limiter.reset("user_1")
        assert limiter.remaining("user_1") == max_requests

    def test_reset_unknown_key_does_not_raise(self) -> None:
        """reset() on a key that was never seen must not raise any exception."""
        limiter = FixedWindow(max_requests=5, window_seconds=60)
        limiter.reset("never_seen")  # must not raise


class TestFixedWindowValidation:
    """Tests for constructor validation."""

    def test_raises_on_zero_max_requests(self) -> None:
        """max_requests=0 must raise InvalidConfigError."""
        with pytest.raises(InvalidConfigError):
            FixedWindow(max_requests=0, window_seconds=60)

    def test_raises_on_zero_window(self) -> None:
        """window_seconds=0 must raise InvalidConfigError."""
        with pytest.raises(InvalidConfigError):
            FixedWindow(max_requests=5, window_seconds=0)

    def test_raises_on_negative_max_requests(self) -> None:
        """max_requests=-1 must raise InvalidConfigError."""
        with pytest.raises(InvalidConfigError):
            FixedWindow(max_requests=-1, window_seconds=60)


class TestFixedWindowProperties:
    """Tests for public properties and window_state()."""

    def test_max_requests_property(self) -> None:
        """max_requests property must reflect the constructor argument."""
        limiter = FixedWindow(max_requests=7, window_seconds=60)
        assert limiter.max_requests == 7

    def test_window_seconds_property(self) -> None:
        """window_seconds property must reflect the constructor argument."""
        limiter = FixedWindow(max_requests=5, window_seconds=30)
        assert limiter.window_seconds == 30

    def test_window_state_unknown_key(self) -> None:
        """window_state on an unseen key returns (max_requests, 0.0, window_seconds)."""
        limiter = FixedWindow(max_requests=5, window_seconds=10)
        remaining, elapsed, total = limiter.window_state("new_key")
        assert remaining == 5
        assert elapsed == 0.0
        assert total == 10.0

    def test_window_state_after_requests(self) -> None:
        """window_state must return a consistent (remaining, elapsed, total) triple."""
        limiter = FixedWindow(max_requests=5, window_seconds=10)
        limiter.is_allowed("user_1")
        limiter.is_allowed("user_1")
        remaining, elapsed, total = limiter.window_state("user_1")
        assert remaining == 3
        assert 0.0 <= elapsed < 10.0
        assert total == 10.0

    def test_window_resets_after_expiry(self) -> None:
        """After the window duration elapses the counter must reset to max."""
        limiter = FixedWindow(max_requests=2, window_seconds=1)
        limiter.is_allowed("user_1")
        limiter.is_allowed("user_1")
        assert limiter.remaining("user_1") == 0
        time.sleep(1.1)
        assert limiter.remaining("user_1") == 2


class TestFixedWindowAllow:
    """Tests for the atomic allow() method."""

    def test_allow_returns_tuple(self) -> None:
        """allow() must return a (bool, int) tuple."""
        limiter = FixedWindow(max_requests=3, window_seconds=60)
        result = limiter.allow("user_1")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_allow_returns_remaining_after_consume(self) -> None:
        """remaining in the tuple must reflect the count after this request."""
        limiter = FixedWindow(max_requests=3, window_seconds=60)
        allowed, remaining = limiter.allow("user_1")
        assert allowed is True
        assert remaining == 2  # max=3, one used → 2 left

    def test_allow_denied_remaining_is_zero(self) -> None:
        """When the window is full the returned remaining must be 0."""
        limiter = FixedWindow(max_requests=1, window_seconds=60)
        limiter.allow("user_1")  # consume the only slot
        allowed, remaining = limiter.allow("user_1")
        assert allowed is False
        assert remaining == 0
