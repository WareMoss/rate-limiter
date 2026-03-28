"""Tests for the Redis-backed Fixed Window rate limiter."""

import pytest
import fakeredis

from app.exceptions import InvalidConfigError
from app.redis_fixed_window import RedisFixedWindow


@pytest.fixture()
def client() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis()


@pytest.fixture()
def limiter(client: fakeredis.FakeRedis) -> RedisFixedWindow:
    return RedisFixedWindow(client, max_requests=5, window_seconds=60)


class TestRedisFixedWindowValidation:
    def test_raises_on_zero_max_requests(self, client: fakeredis.FakeRedis) -> None:
        with pytest.raises(InvalidConfigError):
            RedisFixedWindow(client, max_requests=0, window_seconds=60)

    def test_raises_on_negative_max_requests(self, client: fakeredis.FakeRedis) -> None:
        with pytest.raises(InvalidConfigError):
            RedisFixedWindow(client, max_requests=-1, window_seconds=60)

    def test_raises_on_zero_window(self, client: fakeredis.FakeRedis) -> None:
        with pytest.raises(InvalidConfigError):
            RedisFixedWindow(client, max_requests=5, window_seconds=0)


class TestRedisFixedWindowProperties:
    def test_max_requests_property(self, limiter: RedisFixedWindow) -> None:
        assert limiter.max_requests == 5

    def test_window_seconds_property(self, limiter: RedisFixedWindow) -> None:
        assert limiter.window_seconds == 60


class TestRedisFixedWindowAllowance:
    def test_allows_first_request(self, limiter: RedisFixedWindow) -> None:
        allowed, _ = limiter.allow("u1")
        assert allowed is True

    def test_blocks_when_limit_reached(self, limiter: RedisFixedWindow) -> None:
        for _ in range(5):
            limiter.allow("u1")
        allowed, remaining = limiter.allow("u1")
        assert allowed is False
        assert remaining == 0

    def test_different_keys_are_independent(self, limiter: RedisFixedWindow) -> None:
        for _ in range(5):
            limiter.allow("a")
        allowed, _ = limiter.allow("b")
        assert allowed is True

    def test_remaining_decrements(self, limiter: RedisFixedWindow) -> None:
        _, r0 = limiter.allow("u")
        assert r0 == 4
        _, r1 = limiter.allow("u")
        assert r1 == 3


class TestRedisFixedWindowRemaining:
    def test_remaining_full_for_unknown_key(self, limiter: RedisFixedWindow) -> None:
        assert limiter.remaining("ghost") == 5

    def test_remaining_decreases_after_requests(self, limiter: RedisFixedWindow) -> None:
        limiter.allow("u")
        limiter.allow("u")
        assert limiter.remaining("u") == 3


class TestRedisFixedWindowWindowState:
    def test_window_state_unknown_key(self, limiter: RedisFixedWindow) -> None:
        remaining, elapsed, total = limiter.window_state("ghost")
        assert remaining == 5
        assert elapsed == 0.0
        assert total == 60.0

    def test_window_state_after_requests(self, limiter: RedisFixedWindow) -> None:
        limiter.allow("u")
        limiter.allow("u")
        remaining, elapsed, total = limiter.window_state("u")
        assert remaining == 3
        assert elapsed >= 0.0
        assert total == 60.0


class TestRedisFixedWindowReset:
    def test_reset_restores_full_quota(self, limiter: RedisFixedWindow) -> None:
        for _ in range(5):
            limiter.allow("u")
        limiter.reset("u")
        allowed, _ = limiter.allow("u")
        assert allowed is True

    def test_reset_unknown_key_does_not_raise(self, limiter: RedisFixedWindow) -> None:
        limiter.reset("no-such-key")
