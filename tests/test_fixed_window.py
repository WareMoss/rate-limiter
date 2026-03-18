"""
Unit tests for FixedWindow rate limiter.
All tests written BEFORE implementation — TDD red phase.
"""

import pytest

from app.exceptions import InvalidConfigError
from app.fixed_window import FixedWindow


class TestFixedWindowAllowance:
    """Tests for core allow/block behaviour."""

    def test_allows_first_request(self) -> None:
        limiter = FixedWindow(max_requests=5, window_seconds=60)
        assert limiter.is_allowed("user_1") is True

    def test_blocks_when_limit_reached(self) -> None:
        limiter = FixedWindow(max_requests=2, window_seconds=60)
        limiter.is_allowed("user_1")
        limiter.is_allowed("user_1")
        assert limiter.is_allowed("user_1") is False

    def test_different_keys_are_independent(self) -> None:
        limiter = FixedWindow(max_requests=1, window_seconds=60)
        limiter.is_allowed("user_1")
        assert limiter.is_allowed("user_2") is True

    def test_remaining_decrements_correctly(self) -> None:
        limiter = FixedWindow(max_requests=3, window_seconds=60)
        limiter.is_allowed("user_1")
        assert limiter.remaining("user_1") == 2


class TestFixedWindowReset:
    """Tests for reset behaviour."""

    def test_reset_restores_full_allowance(self) -> None:
        limiter = FixedWindow(max_requests=2, window_seconds=60)
        limiter.is_allowed("user_1")
        limiter.reset("user_1")
        assert limiter.remaining("user_1") == 2

    def test_reset_unknown_key_does_not_raise(self) -> None:
        limiter = FixedWindow(max_requests=2, window_seconds=60)
        limiter.reset("ghost_user")


class TestFixedWindowValidation:
    """Tests for invalid configuration."""

    def test_raises_on_zero_max_requests(self) -> None:
        with pytest.raises(InvalidConfigError):
            FixedWindow(max_requests=0, window_seconds=60)

    def test_raises_on_zero_window(self) -> None:
        with pytest.raises(InvalidConfigError):
            FixedWindow(max_requests=5, window_seconds=0)

    def test_raises_on_negative_max_requests(self) -> None:
        with pytest.raises(InvalidConfigError):
            FixedWindow(max_requests=-1, window_seconds=60)
