"""Redis-backed Sliding Window rate limiting algorithm."""

import time

import redis as redis_lib

from app.base import RateLimiter
from app.exceptions import InvalidConfigError

# Uses a sorted set — score = timestamp_ms, member = unique string.
# A per-key sequence counter (INCR on KEYS[2]) guarantees unique members
# even when multiple requests arrive within the same millisecond.
_ALLOW_SCRIPT = """
local key     = KEYS[1]
local seq_key = KEYS[2]
local max_req  = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local now_ms   = tonumber(ARGV[3])

local cutoff = now_ms - window_ms
redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
local count = tonumber(redis.call('ZCARD', key))

if count < max_req then
    local seq = redis.call('INCR', seq_key)
    local member = tostring(now_ms) .. ':' .. tostring(seq)
    redis.call('ZADD', key, now_ms, member)
    redis.call('PEXPIRE', key, window_ms + 1000)
    redis.call('PEXPIRE', seq_key, window_ms + 1000)
    return {1, max_req - count - 1}
else
    return {0, 0}
end
"""


class RedisSlidingWindow(RateLimiter):
    """Sliding Window backed by a Redis sorted set.

    Each allowed request is stored as a ZSET member scored by timestamp.
    Expired members are evicted inside the same Lua script that checks the
    count, so eviction and the allow decision are always atomic.
    """

    def __init__(
        self,
        client: redis_lib.Redis,  # type: ignore[type-arg]
        max_requests: int,
        window_seconds: int,
        key_prefix: str = "rl:sw:",
    ) -> None:
        if max_requests <= 0:
            raise InvalidConfigError(f"max_requests must be > 0, got {max_requests}")
        if window_seconds <= 0:
            raise InvalidConfigError(
                f"window_seconds must be > 0, got {window_seconds}"
            )

        self._client = client
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._window_ms = window_seconds * 1000
        self._prefix = key_prefix
        self._allow_sha: str = client.script_load(_ALLOW_SCRIPT)

    @property
    def max_requests(self) -> int:
        return self._max_requests

    @property
    def window_seconds(self) -> int:
        return self._window_seconds

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def _seq_key(self, key: str) -> str:
        return f"{self._prefix}{key}:seq"

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    def allow(self, key: str) -> tuple[bool, int]:
        result = self._client.evalsha(
            self._allow_sha, 2, self._key(key), self._seq_key(key),
            self._max_requests, self._window_ms, self._now_ms(),
        )
        return bool(result[0]), int(result[1])

    def remaining(self, key: str) -> int:
        rkey = self._key(key)
        now_ms = self._now_ms()
        pipe = self._client.pipeline()
        pipe.zremrangebyscore(rkey, 0, now_ms - self._window_ms)
        pipe.zcard(rkey)
        _, count = pipe.execute()
        return max(0, self._max_requests - int(count))

    def window_state(self, key: str) -> tuple[int, float, float]:
        """Return (remaining, oldest_request_age_secs, window_size_secs)."""
        rkey = self._key(key)
        now_ms = self._now_ms()
        total = float(self._window_seconds)

        pipe = self._client.pipeline()
        pipe.zremrangebyscore(rkey, 0, now_ms - self._window_ms)
        pipe.zcard(rkey)
        pipe.zrange(rkey, 0, 0, withscores=True)
        _, count, oldest = pipe.execute()

        count = int(count)
        remaining = max(0, self._max_requests - count)
        if oldest:
            oldest_ms = float(oldest[0][1])
            oldest_age = (now_ms - oldest_ms) / 1000.0
        else:
            oldest_age = 0.0
        return remaining, max(0.0, oldest_age), total

    def reset(self, key: str) -> None:
        self._client.delete(self._key(key), self._seq_key(key))
