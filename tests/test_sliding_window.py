"""Tests for the SlidingWindow rate limiter."""

import time

import pytest

from app.exceptions import InvalidConfigError
from app.sliding_window import SlidingWindow


class TestSlidingWindowValidation:
    def test_raises_on_zero_max_requests(self) -> None:
        with pytest.raises(InvalidConfigError):
            SlidingWindow(max_requests=0, window_seconds=10)

    def test_raises_on_negative_max_requests(self) -> None:
        with pytest.raises(InvalidConfigError):
            SlidingWindow(max_requests=-1, window_seconds=10)

    def test_raises_on_zero_window(self) -> None:
        with pytest.raises(InvalidConfigError):
            SlidingWindow(max_requests=5, window_seconds=0)

    def test_raises_on_negative_window(self) -> None:
        with pytest.raises(InvalidConfigError):
            SlidingWindow(max_requests=5, window_seconds=-1)


class TestSlidingWindowProperties:
    def test_max_requests_property(self) -> None:
        sw = SlidingWindow(max_requests=5, window_seconds=10)
        assert sw.max_requests == 5

    def test_window_seconds_property(self) -> None:
        sw = SlidingWindow(max_requests=5, window_seconds=30)
        assert sw.window_seconds == 30

    def test_window_state_unknown_key(self) -> None:
        sw = SlidingWindow(max_requests=5, window_seconds=10)
        remaining, age, total = sw.window_state("ghost")
        assert remaining == 5
        assert age == 0.0
        assert total == 10.0

    def test_window_state_after_requests(self) -> None:
        sw = SlidingWindow(max_requests=5, window_seconds=10)
        sw.allow("k")
        sw.allow("k")
        remaining, age, total = sw.window_state("k")
        assert remaining == 3
        assert age >= 0.0
        assert total == 10.0


class TestSlidingWindowAllowance:
    def test_allows_first_request(self) -> None:
        sw = SlidingWindow(max_requests=3, window_seconds=10)
        allowed, _ = sw.allow("u1")
        assert allowed is True

    def test_blocks_when_limit_reached(self) -> None:
        sw = SlidingWindow(max_requests=2, window_seconds=10)
        sw.allow("u1")
        sw.allow("u1")
        allowed, remaining = sw.allow("u1")
        assert allowed is False
        assert remaining == 0

    def test_different_keys_are_independent(self) -> None:
        sw = SlidingWindow(max_requests=1, window_seconds=10)
        sw.allow("a")
        allowed, _ = sw.allow("b")
        assert allowed is True

    def test_remaining_decrements_correctly(self) -> None:
        sw = SlidingWindow(max_requests=3, window_seconds=10)
        _, r0 = sw.allow("u")
        assert r0 == 2
        _, r1 = sw.allow("u")
        assert r1 == 1
        _, r2 = sw.allow("u")
        assert r2 == 0


class TestSlidingWindowReset:
    def test_reset_restores_full_allowance(self) -> None:
        sw = SlidingWindow(max_requests=2, window_seconds=10)
        sw.allow("u")
        sw.allow("u")
        sw.reset("u")
        allowed, remaining = sw.allow("u")
        assert allowed is True
        assert remaining == 1

    def test_reset_unknown_key_does_not_raise(self) -> None:
        sw = SlidingWindow(max_requests=2, window_seconds=10)
        sw.reset("no-such-key")  # must not raise


class TestSlidingWindowAllow:
    def test_allow_returns_tuple(self) -> None:
        sw = SlidingWindow(max_requests=5, window_seconds=10)
        result = sw.allow("u")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_allow_returns_remaining_after_consume(self) -> None:
        sw = SlidingWindow(max_requests=5, window_seconds=10)
        _, remaining = sw.allow("u")
        assert remaining == 4

    def test_allow_denied_remaining_is_zero(self) -> None:
        sw = SlidingWindow(max_requests=1, window_seconds=10)
        sw.allow("u")
        _, remaining = sw.allow("u")
        assert remaining == 0


class TestSlidingWindowExpiry:
    def test_old_requests_fall_out_after_window(self) -> None:
        sw = SlidingWindow(max_requests=2, window_seconds=1)
        sw.allow("u")
        sw.allow("u")
        assert sw.remaining("u") == 0
        time.sleep(1.1)
        assert sw.remaining("u") == 2

    def test_boundary_burst_is_blocked(self) -> None:
        """The key difference from FixedWindow.

        With a 1-second window and limit of 2: make 2 requests near the end
        of the window, then 2 more immediately after. SlidingWindow must block
        the third request because all 4 timestamps fall within the same 1-second
        sliding window, unlike FixedWindow which resets on a boundary.
        """
        sw = SlidingWindow(max_requests=2, window_seconds=1)
        sw.allow("u")
        sw.allow("u")
        # Both slots used — next must be denied, no boundary reset
        allowed, _ = sw.allow("u")
        assert allowed is False
