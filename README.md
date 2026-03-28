# Rate Limiter

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Tests](https://img.shields.io/badge/tests-passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-%3E90%25-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue)
![Made with love](https://img.shields.io/badge/made%20with-%E2%9D%A4-red)

A Python library implementing two production-ready rate limiting algorithms: Token Bucket and Fixed Window. Both share a common abstract interface so they are interchangeable anywhere a `RateLimiter` is accepted. A FastAPI wrapper exposes the library over HTTP for integration testing and demonstration.

---

## Algorithms

| Algorithm | How it works | Burst handling | Boundary spike |
|---|---|---|---|
| **Token Bucket** | Tokens accumulate at a fixed rate up to a capacity ceiling. Each request consumes one token. | Absorbs bursts up to `capacity` | No |
| **Fixed Window** | Counts requests within a fixed time slot. Counter resets when the window expires. | None — limit is hard per window | Yes — two windows back-to-back can double throughput |

Use **Token Bucket** when you want to allow short bursts while enforcing a sustained average rate.
Use **Fixed Window** when simplicity and predictable resets matter more than burst control.

---

## Complexity

| Algorithm | Time (per request) | Space |
|---|---|---|
| Token Bucket | O(1) | O(n) — one entry per unique key |
| Fixed Window | O(1) | O(n) — one entry per unique key |

Both algorithms use a dictionary keyed by caller identifier. All operations (lookup, update, reset) are O(1) regardless of the number of tracked keys.

---

## Installation

```bash
pip install -r requirements.txt
```

---

## Usage

### Token Bucket

```python
from app.token_bucket import TokenBucket

limiter = TokenBucket(capacity=10, refill_rate=1.0)

if limiter.is_allowed("user_123"):
    print(f"Allowed. Remaining: {limiter.remaining('user_123')}")
else:
    print("Rate limit exceeded.")

# Reset a specific key
limiter.reset("user_123")
```

### Fixed Window

```python
from app.fixed_window import FixedWindow

limiter = FixedWindow(max_requests=100, window_seconds=60)

if limiter.is_allowed("ip_10.0.0.1"):
    print(f"Allowed. Remaining: {limiter.remaining('ip_10.0.0.1')}")
else:
    print("Rate limit exceeded.")
```

### Polymorphic usage

```python
from app.base import RateLimiter
from app.token_bucket import TokenBucket
from app.fixed_window import FixedWindow

def process_request(limiter: RateLimiter, key: str) -> bool:
    return limiter.is_allowed(key)

# Either implementation works — same interface
process_request(TokenBucket(capacity=5, refill_rate=1.0), "user_1")
process_request(FixedWindow(max_requests=5, window_seconds=10), "user_1")
```

---

## API

Start the server:

```bash
uvicorn api.server:app --reload
```

### `POST /check`

Check whether a request is allowed.

**Request body:**
```json
{ "key": "user_1", "algorithm": "token_bucket" }
```

**Response:**
```json
{ "allowed": true, "remaining": 9, "algorithm": "token_bucket", "key": "user_1" }
```

### `POST /reset`

Reset the rate limit state for a key.

**Request body:**
```json
{ "key": "user_1", "algorithm": "fixed_window" }
```

**Response:**
```json
{ "reset": true, "key": "user_1" }
```

### `GET /health`

Liveness probe.

**Response:**
```json
{ "status": "ok" }
```

---

## Running Tests

```bash
pytest
```

Runs all 22 tests with coverage reporting. The suite enforces ≥ 90% coverage and will fail the run if coverage drops below that threshold.

To run linting and type checks:

```bash
ruff check app/ tests/
mypy app/
```

---

## Project Structure

```
rate-limiter/
├── .github/
│   └── workflows/
│       └── ci.yml          # GitHub Actions: lint, type check, test
├── app/
│   ├── __init__.py
│   ├── base.py             # Abstract RateLimiter interface
│   ├── exceptions.py       # InvalidConfigError, RateLimitExceededError
│   ├── fixed_window.py     # Fixed Window implementation
│   └── token_bucket.py     # Token Bucket implementation
├── api/
│   └── server.py           # FastAPI HTTP wrapper
├── tests/
│   ├── __init__.py
│   ├── test_fixed_window.py
│   └── test_token_bucket.py
├── .gitignore
├── pyproject.toml
├── requirements.txt
└── README.md
```
