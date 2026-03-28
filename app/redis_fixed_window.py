"""Redis-backed Fixed Window rate limiting algorithm."""

import time

import redis as redis_lib

from app.base import RateLimiter
from app.exceptions import InvalidConfigError

# Atomically increment the counter and set TTL on first touch.
# Returns {allowed, remaining}.
_ALLOW_SCRIPT = """
local count = tonumber(redis.call('INCR', KEYS[1]))
local max   = tonumber(ARGV[1])
local ttl   = tonumber(ARGV[2])

if count == 1 then
    redis.call('SET', KEYS[2], tostring(ARGV[3]))
    redis.call('EXPIRE', KEYS[1], ttl)
    redis.call('EXPIRE', KEYS[2], ttl)
end

if count <= max then
    return {1, max - count}
else
    return {0, 0}
end
"""


class RedisFixedWindow(RateLimiter):
    """Fixed Window that stores its counter in Redis.

    Window boundaries are derived from wall-clock time so every instance
    landing on the same Redis server shares the same window automatically.
    """

    def __init__(
        self,
        client: redis_lib.Redis,  # type: ignore[type-arg]
        max_requests: int,
        window_seconds: int,
        key_prefix: str = "rl:fw:",
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
        self._prefix = key_prefix
        self._allow_sha: str = client.script_load(_ALLOW_SCRIPT)

    @property
    def max_requests(self) -> int:
        return self._max_requests

    @property
    def window_seconds(self) -> int:
        return self._window_seconds

    def _window_id(self) -> int:
        return int(time.time() / self._window_seconds)

    def _keys(self, key: str) -> tuple[str, str]:
        wid = self._window_id()
        return f"{self._prefix}{key}:{wid}", f"{self._prefix}{key}:{wid}:start"

    def allow(self, key: str) -> tuple[bool, int]:
        count_key, start_key = self._keys(key)
        now_ms = int(time.time() * 1000)
        result = self._client.evalsha(
            self._allow_sha, 2, count_key, start_key,
            self._max_requests, self._window_seconds, now_ms,
        )
        return bool(result[0]), int(result[1])

    def remaining(self, key: str) -> int:
        count_key, _ = self._keys(key)
        raw = self._client.get(count_key)
        if raw is None:
            return self._max_requests
        return max(0, self._max_requests - int(raw))

    def window_state(self, key: str) -> tuple[int, float, float]:
        """Return (remaining, elapsed_secs, total_secs)."""
        count_key, start_key = self._keys(key)
        raw_count, raw_start = self._client.mget(count_key, start_key)
        total = float(self._window_seconds)
        if raw_count is None:
            return self._max_requests, 0.0, total
        count = int(raw_count)
        remaining = max(0, self._max_requests - count)
        window_start_ms = int(raw_start) if raw_start else int(time.time() * 1000)
        elapsed = (time.time() * 1000 - window_start_ms) / 1000.0
        return remaining, max(0.0, elapsed), total

    def reset(self, key: str) -> None:
        count_key, start_key = self._keys(key)
        self._client.delete(count_key, start_key)
