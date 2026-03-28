"""Tests for the Redis-backed Token Bucket rate limiter."""

import pytest
import fakeredis

from app.exceptions import InvalidConfigError
from app.redis_token_bucket import RedisTokenBucket


@pytest.fixture()
def client() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis()


@pytest.fixture()
def limiter(client: fakeredis.FakeRedis) -> RedisTokenBucket:
    return RedisTokenBucket(client, capacity=5, refill_rate=0.0)


class TestRedisTokenBucketValidation:
    def test_raises_on_zero_capacity(self, client: fakeredis.FakeRedis) -> None:
        with pytest.raises(InvalidConfigError):
            RedisTokenBucket(client, capacity=0, refill_rate=1.0)

    def test_raises_on_negative_capacity(self, client: fakeredis.FakeRedis) -> None:
        with pytest.raises(InvalidConfigError):
            RedisTokenBucket(client, capacity=-1, refill_rate=1.0)

    def test_raises_on_negative_refill_rate(self, client: fakeredis.FakeRedis) -> None:
        with pytest.raises(InvalidConfigError):
            RedisTokenBucket(client, capacity=5, refill_rate=-0.1)


class TestRedisTokenBucketProperties:
    def test_capacity_property(self, limiter: RedisTokenBucket) -> None:
        assert limiter.capacity == 5


class TestRedisTokenBucketAllowance:
    def test_allows_first_request(self, limiter: RedisTokenBucket) -> None:
        allowed, _ = limiter.allow("u1")
        assert allowed is True

    def test_blocks_when_empty(self, limiter: RedisTokenBucket) -> None:
        for _ in range(5):
            limiter.allow("u1")
        allowed, remaining = limiter.allow("u1")
        assert allowed is False
        assert remaining == 0

    def test_different_keys_are_independent(self, limiter: RedisTokenBucket) -> None:
        for _ in range(5):
            limiter.allow("a")
        allowed, _ = limiter.allow("b")
        assert allowed is True

    def test_remaining_decrements(self, limiter: RedisTokenBucket) -> None:
        _, r0 = limiter.allow("u")
        assert r0 == 4
        _, r1 = limiter.allow("u")
        assert r1 == 3


class TestRedisTokenBucketRemaining:
    def test_remaining_full_for_unknown_key(self, limiter: RedisTokenBucket) -> None:
        assert limiter.remaining("ghost") == 5

    def test_remaining_decreases_after_requests(self, limiter: RedisTokenBucket) -> None:
        limiter.allow("u")
        limiter.allow("u")
        assert limiter.remaining("u") == 3


class TestRedisTokenBucketReset:
    def test_reset_restores_full_quota(self, limiter: RedisTokenBucket) -> None:
        for _ in range(5):
            limiter.allow("u")
        limiter.reset("u")
        allowed, _ = limiter.allow("u")
        assert allowed is True

    def test_reset_unknown_key_does_not_raise(self, limiter: RedisTokenBucket) -> None:
        limiter.reset("no-such-key")
