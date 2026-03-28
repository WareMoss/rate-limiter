"""Redis-backed Token Bucket rate limiting algorithm."""

import time

import redis as redis_lib

from app.base import RateLimiter
from app.exceptions import InvalidConfigError

# Atomic refill + consume in a single round-trip.
# Uses wall-clock milliseconds because Redis doesn't share time.monotonic().
_ALLOW_SCRIPT = """
local tokens_str     = redis.call('HGET', KEYS[1], 'tokens')
local last_refill_str = redis.call('HGET', KEYS[1], 'last_refill_ms')
local capacity   = tonumber(ARGV[1])
local rate       = tonumber(ARGV[2])
local now_ms     = tonumber(ARGV[3])

local tokens, last_ms
if tokens_str == false then
    tokens  = capacity
    last_ms = now_ms
else
    tokens  = tonumber(tokens_str)
    last_ms = tonumber(last_refill_str)
end

local elapsed = (now_ms - last_ms) / 1000.0
local earned  = elapsed * rate
if earned > 0 then
    tokens = math.min(capacity, tokens + earned)
end

local allowed   = 0
local remaining = math.floor(tokens)

if tokens >= 1.0 then
    tokens   = tokens - 1.0
    remaining = math.floor(tokens)
    allowed  = 1
end

redis.call('HSET', KEYS[1], 'tokens', tostring(tokens), 'last_refill_ms', tostring(now_ms))
return {allowed, remaining}
"""

_REMAINING_SCRIPT = """
local tokens_str      = redis.call('HGET', KEYS[1], 'tokens')
local last_refill_str = redis.call('HGET', KEYS[1], 'last_refill_ms')
local capacity = tonumber(ARGV[1])
local rate     = tonumber(ARGV[2])
local now_ms   = tonumber(ARGV[3])

if tokens_str == false then
    return capacity
end

local tokens  = tonumber(tokens_str)
local last_ms = tonumber(last_refill_str)
local elapsed = (now_ms - last_ms) / 1000.0
local earned  = elapsed * rate
tokens = math.min(capacity, tokens + earned)
return math.floor(tokens)
"""


class RedisTokenBucket(RateLimiter):
    """Token Bucket that stores state in Redis rather than in-process memory.

    Accepts a redis.Redis client at construction time so the caller controls
    connection pooling and config. Everything else behaves like TokenBucket.
    """

    def __init__(
        self,
        client: redis_lib.Redis,  # type: ignore[type-arg]
        capacity: int,
        refill_rate: float,
        key_prefix: str = "rl:tb:",
    ) -> None:
        if capacity <= 0:
            raise InvalidConfigError(f"capacity must be > 0, got {capacity}")
        if refill_rate < 0:
            raise InvalidConfigError(f"refill_rate must be >= 0, got {refill_rate}")

        self._client = client
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._prefix = key_prefix
        self._allow_sha: str = client.script_load(_ALLOW_SCRIPT)
        self._remaining_sha: str = client.script_load(_REMAINING_SCRIPT)

    @property
    def capacity(self) -> int:
        return self._capacity

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    def allow(self, key: str) -> tuple[bool, int]:
        result = self._client.evalsha(
            self._allow_sha, 1, self._key(key),
            self._capacity, self._refill_rate, self._now_ms(),
        )
        return bool(result[0]), int(result[1])

    def remaining(self, key: str) -> int:
        result = self._client.evalsha(
            self._remaining_sha, 1, self._key(key),
            self._capacity, self._refill_rate, self._now_ms(),
        )
        return int(result)

    def reset(self, key: str) -> None:
        self._client.delete(self._key(key))
