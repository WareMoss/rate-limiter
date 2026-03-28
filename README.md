## WARNING ##

Claude Ai was used to make this README pretty as well as improve the UI and readability of my comments. I also used it to rip apart and suggest improvements and fixtures to my code.

# Rate Limiter

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Tests](https://img.shields.io/badge/tests-94%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-%3E90%25-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue)

A Python rate limiting library with three algorithms and two storage backends. All implementations share a common abstract interface so they are interchangeable anywhere a `RateLimiter` is accepted. A FastAPI wrapper exposes them over HTTP, and a live dashboard lets you visualise the algorithms in action.

---

## Algorithms

| Algorithm | How it works | Boundary burst |
|---|---|---|
| **Token Bucket** | Tokens refill at a fixed rate up to a capacity ceiling. Each request consumes one token. | No |
| **Fixed Window** | Counts requests in a fixed time slot. Counter resets when the window expires. | Yes — requests at the tail of one window plus requests at the head of the next can briefly double throughput |
| **Sliding Window** | Tracks the timestamp of every request and counts only those within the last N seconds. | No — the limit holds across any rolling slice of the window, not just aligned buckets |

**Token Bucket** — good when short bursts are acceptable but you want a sustained average enforced.
**Fixed Window** — simplest to reason about; predictable resets.
**Sliding Window** — strictest; no boundary loophole, at the cost of O(max\_requests) memory per key.

---

## Storage backends

Each algorithm ships with an in-memory implementation (default) and a Redis-backed one.

| Class | Backend |
|---|---|
| `TokenBucket` | in-memory |
| `FixedWindow` | in-memory |
| `SlidingWindow` | in-memory |
| `RedisTokenBucket` | Redis (Lua script — atomic refill + consume) |
| `RedisFixedWindow` | Redis (Lua script — atomic INCR + TTL) |
| `RedisSlidingWindow` | Redis sorted set (Lua script — atomic evict + check + add) |

The server picks which backend to use at startup. Set `REDIS_URL` to switch to Redis; leave it unset and it runs in-memory. The HTTP API is identical either way.

---

## Complexity

| Algorithm | Time | Space |
|---|---|---|
| Token Bucket | O(1) | O(n) keys |
| Fixed Window | O(1) | O(n) keys |
| Sliding Window | O(r) per request where r = requests in window | O(max\_requests) per key |

Token Bucket and Fixed Window use a dict keyed by caller ID — all operations are O(1). Sliding Window evicts expired timestamps on each call, which is bounded by the window size.

---

## Running the dashboard

```bash
uvicorn api.server:app --reload
```

Then open http://localhost:8000. The dashboard shows live visualisations for all three algorithms and lets you fire individual requests, flood a key, or reset state. There is also a **Run Tests** button that executes the full pytest suite and displays per-test results in the browser.

To use Redis instead of in-memory state:

```bash
REDIS_URL=redis://localhost:6379 uvicorn api.server:app --reload
```

---

## Library usage

### Token Bucket

```python
from app.token_bucket import TokenBucket

limiter = TokenBucket(capacity=10, refill_rate=1.0)

allowed, remaining = limiter.allow("user_123")
if allowed:
    print(f"OK — {remaining} tokens left")
else:
    print("Rate limit exceeded")

limiter.reset("user_123")
```

### Fixed Window

```python
from app.fixed_window import FixedWindow

limiter = FixedWindow(max_requests=100, window_seconds=60)
allowed, remaining = limiter.allow("ip_10.0.0.1")
```

### Sliding Window

```python
from app.sliding_window import SlidingWindow

limiter = SlidingWindow(max_requests=100, window_seconds=60)
allowed, remaining = limiter.allow("user_123")
```

### Redis backends

```python
import redis
from app.redis_token_bucket import RedisTokenBucket

client = redis.Redis.from_url("redis://localhost:6379")
limiter = RedisTokenBucket(client, capacity=10, refill_rate=1.0)
allowed, remaining = limiter.allow("user_123")
```

### Polymorphic usage

All six classes implement `RateLimiter`, so you can swap backends without touching call sites:

```python
from app.base import RateLimiter

def handle(limiter: RateLimiter, key: str) -> bool:
    allowed, _ = limiter.allow(key)
    return allowed
```

---

## HTTP API

### `POST /check`

Check whether a request is allowed (and consume a slot).

```json
{ "key": "user_1", "algorithm": "token_bucket" }
```

`algorithm` accepts `token_bucket`, `fixed_window`, or `sliding_window`.

```json
{ "allowed": true, "remaining": 9, "algorithm": "token_bucket", "key": "user_1" }
```

### `POST /reset`

Clear state for a key.

```json
{ "key": "user_1", "algorithm": "sliding_window" }
```

### `GET /state/{algorithm}/{key}`

Current quota state — polled by the dashboard.

### `GET /health`

```json
{ "status": "ok", "backend": "memory" }
```

`backend` is `"memory"` or `"redis"` depending on how the server was started.

---

## Running tests

```bash
pytest
```

94 tests across all six implementations. Coverage is enforced at ≥ 90% and will fail the run if it drops. Redis tests use `fakeredis` so no running Redis instance is needed.

```bash
ruff check app/ tests/
mypy app/
```

---

## Project structure

```
rate-limiter/
├── .github/
│   └── workflows/
│       └── ci.yml                  # lint → typecheck → pytest
├── app/
│   ├── base.py                     # RateLimiter ABC
│   ├── exceptions.py
│   ├── token_bucket.py
│   ├── fixed_window.py
│   ├── sliding_window.py
│   ├── redis_token_bucket.py
│   ├── redis_fixed_window.py
│   └── redis_sliding_window.py
├── api/
│   └── server.py                   # FastAPI wrapper
├── static/
│   └── index.html                  # live dashboard
├── tests/
│   ├── test_token_bucket.py
│   ├── test_fixed_window.py
│   ├── test_sliding_window.py
│   ├── test_redis_token_bucket.py
│   ├── test_redis_fixed_window.py
│   └── test_redis_sliding_window.py
├── pyproject.toml
├── requirements.txt
└── LICENSE
```
