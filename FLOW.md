# Program Flow — Rate Limiter

A walkthrough of exactly what happens at each stage, written for debugging with breakpoints.

---

## 1. Server startup

**Entry point:** `uvicorn api.server:app --reload`

Uvicorn imports `api/server.py`. Python runs the module top-to-bottom at import time:

1. `os.environ.get("REDIS_URL")` is checked.
   - If unset (default): three in-memory limiters are created and stored as module-level variables:
     ```
     _token_bucket  = TokenBucket(capacity=10, refill_rate=1.0)
     _fixed_window  = FixedWindow(max_requests=10, window_seconds=60)
     _sliding_window = SlidingWindow(max_requests=10, window_seconds=60)
     ```
   - If set: the Redis-backed equivalents are created instead.
2. The FastAPI `app` object is created and middleware is registered.
3. All route handlers (`@app.get`, `@app.post`) are registered but not called yet.
4. Uvicorn starts listening on port 8000.

**Breakpoint opportunity:** put a breakpoint on the `_token_bucket = TokenBucket(...)` line in `server.py` to inspect which branch runs and what the initial state looks like.

---

## 2. Browser opens the dashboard

**Request:** `GET /`

**Route:** `api/server.py` → `def index()`

FastAPI serves `static/index.html` as a static file. No rate limiter logic runs here.

Once the HTML loads in the browser, two things begin immediately:

- **`pollState()`** — a JavaScript function that runs every 1000 ms (1 second). It calls `GET /state/token_bucket/demo`, `GET /state/fixed_window/demo`, and `GET /state/sliding_window/demo` in parallel. This is what keeps the three algorithm cards on the dashboard updated live.
- The page waits for user interaction (button clicks).

---

## 3. Clicking "Check" — the happy path

**User action:** type a key (e.g. `user_1`), select an algorithm, click **Check**.

**What the browser does:** sends a `POST /check` with JSON body:
```json
{ "key": "user_1", "algorithm": "token_bucket" }
```

**Route:** `api/server.py` → `def check(body, token_bucket, fixed_window, sliding_window)`

FastAPI first calls the three dependency functions:
- `get_token_bucket()` → returns `_token_bucket` (the module-level instance)
- `get_fixed_window()` → returns `_fixed_window`
- `get_sliding_window()` → returns `_sliding_window`

Then `_resolve_limiter()` picks the right one based on `body.algorithm`.

Then `limiter.allow(body.key)` is called. See section 4 for what happens inside each algorithm.

The response is:
```json
{ "allowed": true, "remaining": 9, "algorithm": "token_bucket", "key": "user_1" }
```

The browser adds a green entry to the log panel.

**Breakpoint opportunity:** put a breakpoint on `allowed, remaining = limiter.allow(body.key)` in `server.py` to inspect which limiter instance was resolved and what key was passed.

---

## 4. Inside `allow()` — per algorithm

### Token Bucket (`app/token_bucket.py`)

1. Acquires `threading.Lock` (prevents two requests racing).
2. `_get_or_create(key)` — looks up `_buckets[key]`. If not found, creates a new `_BucketState` with `tokens = capacity` (starts full).
3. `_refill(state)` — calculates how much time has passed since the last request using `time.monotonic()`. Multiplies elapsed seconds × `refill_rate` to get earned tokens. Adds them, capped at `capacity`.
4. Checks `state.tokens >= 1.0`. If yes: subtracts 1 token, returns `(True, remaining)`. If no: returns `(False, 0)`.

**Key data:** `_buckets` dict — each key maps to a `_BucketState(tokens, last_refill)`.

**Breakpoint opportunity:** breakpoint on `_refill()` to watch the token math. Inspect `elapsed`, `earned`, and `state.tokens` before and after.

---

### Fixed Window (`app/fixed_window.py`)

1. Acquires `threading.Lock`.
2. `_get_or_create(key)` — looks up `_windows[key]`. If not found, creates `_WindowState(count=0, window_start=now)`.
3. `_maybe_reset(state)` — checks if `time.monotonic() - state.window_start >= window_seconds`. If the window has expired, resets `count = 0` and records a new `window_start`.
4. Checks `state.count < max_requests`. If yes: increments count, returns `(True, remaining)`. If no: returns `(False, 0)`.

**Key data:** `_windows` dict — each key maps to `_WindowState(count, window_start)`.

**Breakpoint opportunity:** breakpoint on `_maybe_reset()` — this is where the window resets. You can watch `count` go back to 0. Also breakpoint the `if state.count < self._max_requests` line to see exactly when a request gets denied.

---

### Sliding Window (`app/sliding_window.py`)

1. Acquires `threading.Lock`.
2. `_get_or_create(key)` — looks up `_logs[key]`. Creates a `_WindowLog` with an empty `deque` if not found.
3. `_prune(log, now)` — pops timestamps from the left of the deque while they are older than `now - window_seconds`. This evicts expired entries.
4. Checks `len(log.timestamps) < max_requests`. If yes: appends `now` to the deque, returns `(True, remaining)`. If no: returns `(False, 0)`.

**Key data:** `_logs` dict — each key maps to a `_WindowLog` containing a `deque` of `float` timestamps (monotonic seconds).

**Breakpoint opportunity:** breakpoint on `_prune()` to watch old timestamps being removed. Breakpoint on `log.timestamps.append(now)` to see a new timestamp being recorded.

---

### Redis variants (Token Bucket / Fixed Window / Sliding Window)

Instead of in-memory dicts, state lives in Redis. All logic is written as Lua scripts that run atomically on the Redis server — the Python side just calls `evalsha()` and reads back the result.

- **RedisTokenBucket** (`app/redis_token_bucket.py`) — state is a Redis Hash (`HGET`/`HSET`) storing `tokens` and `last_refill_ms`.
- **RedisFixedWindow** (`app/redis_fixed_window.py`) — state is a Redis string counter (`INCR`). Window ID is derived from `int(time.time() / window_seconds)`, so all server processes share the same window automatically.
- **RedisSlidingWindow** (`app/redis_sliding_window.py`) — state is a Redis Sorted Set (`ZADD`/`ZCARD`). Each request is a member scored by its timestamp in milliseconds. A sequence counter key (`INCR`) ensures members are unique even within the same millisecond.

**Breakpoint opportunity:** breakpoint on `self._client.evalsha(...)` in any Redis class to inspect the arguments being sent and the raw result that comes back.

---

## 5. Clicking "Flood" — hitting the limit

**What the browser does:** fires 20 `POST /check` requests as fast as possible in a loop.

The first 10 go through (capacity is 10). After that, `allow()` returns `(False, 0)` and the browser adds red entries to the log.

**Breakpoint opportunity:** breakpoint on `return False, 0` in whichever algorithm's `allow()` you care about — you will hit it once the limit is reached.

---

## 6. Clicking "Reset"

**Request:** `POST /reset` with `{ "key": "user_1", "algorithm": "token_bucket" }`

**Route:** `def reset()` in `server.py` — resolves the limiter the same way as `/check`, then calls `limiter.reset(key)`.

- `TokenBucket.reset()` — calls `_buckets.pop(key, None)`. Next `allow()` call for that key starts fresh with a full bucket.
- `FixedWindow.reset()` — calls `_windows.pop(key, None)`. Next call starts a new window at count 0.
- `SlidingWindow.reset()` — calls `_logs.pop(key, None)`. Next call starts with an empty deque.
- Redis variants — calls `client.delete(...)` on the relevant Redis keys.

**Breakpoint opportunity:** breakpoint on `limiter.reset(body.key)` in `server.py`, then step into the implementation to see the dict entry being removed.

---

## 7. The polling loop — `GET /state/{algorithm}/{key}`

Every second the dashboard JavaScript calls all three state endpoints for key `demo`.

**Route:** `def state(algorithm, key, ...)` in `server.py`

- For `token_bucket`: calls `token_bucket.remaining(key)` and returns current token count + capacity.
- For `fixed_window`: calls `fixed_window.window_state(key)` which returns `(remaining, elapsed_secs, total_secs)`. The dashboard uses `elapsed/total` to draw the progress bar.
- For `sliding_window`: calls `sliding_window.window_state(key)` which returns `(remaining, oldest_request_age_secs, window_size_secs)`. The oldest request age tells the dashboard how far into the window the earliest still-active request is.

The JavaScript then updates the ring gauges, progress bars, and countdown labels.

**Breakpoint opportunity:** breakpoint on `return StateResponse(...)` in `server.py` to inspect what values are being sent back to the browser on each poll tick.

---

## 8. Clicking "Run Tests"

**Request:** `GET /tests/run`

**Route:** `def run_tests()` in `server.py`

1. Resolves the project root (`Path(__file__).parent.parent`).
2. Spawns a subprocess: `python -m pytest tests/ -v --no-header --tb=short --override-ini=addopts=`
   - `--override-ini=addopts=` clears the coverage settings from `pyproject.toml` so pytest doesn't try to measure coverage inside a subprocess (which hangs on Windows).
   - `stderr=subprocess.STDOUT` merges stderr into stdout to avoid a Windows pipe deadlock.
3. Waits up to 60 seconds for pytest to finish.
4. Parses the output with regex — extracts each `tests/foo.py::test_name PASSED/FAILED` line.
5. Returns a JSON response listing every test and its status.

The browser renders a grid of green/red test result pills.

---

## Data flow summary

```
Browser click
    │
    ▼
POST /check  (JSON body)
    │
    ▼
server.py: check()
    │  resolves limiter via _resolve_limiter()
    ▼
limiter.allow(key)
    │
    ├── TokenBucket.allow()
    │       acquire lock
    │       _get_or_create(key) → _buckets dict
    │       _refill() → add earned tokens
    │       consume 1 token → return (bool, int)
    │
    ├── FixedWindow.allow()
    │       acquire lock
    │       _get_or_create(key) → _windows dict
    │       _maybe_reset() → reset count if window expired
    │       increment count → return (bool, int)
    │
    └── SlidingWindow.allow()
            acquire lock
            _get_or_create(key) → _logs dict
            _prune() → evict old timestamps from deque
            append new timestamp → return (bool, int)
    │
    ▼
CheckResponse → JSON → browser log panel
```

---

## Suggested breakpoint sequence for a first debug session

1. `api/server.py` line 51 — `_token_bucket = TokenBucket(...)` — confirms in-memory path at startup.
2. `api/server.py` → `check()` → `allowed, remaining = limiter.allow(body.key)` — entry point for every request.
3. `app/token_bucket.py` → `_refill()` — watch token math live.
4. `app/fixed_window.py` → `_maybe_reset()` — watch window reset trigger.
5. `app/sliding_window.py` → `_prune()` — watch old timestamps drop off the deque.
6. `api/server.py` → `run_tests()` → `proc = subprocess.run(...)` — watch the pytest subprocess launch.
