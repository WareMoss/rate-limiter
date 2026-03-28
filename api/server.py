"""FastAPI wrapper for the rate limiter library.

Thin HTTP layer only — no business logic lives here. All rate limiting
decisions happen inside app/.
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.base import RateLimiter
from app.fixed_window import FixedWindow
from app.redis_fixed_window import RedisFixedWindow
from app.redis_sliding_window import RedisSlidingWindow
from app.redis_token_bucket import RedisTokenBucket
from app.sliding_window import SlidingWindow
from app.token_bucket import TokenBucket

STATIC_DIR = Path(__file__).parent.parent / "static"

app = FastAPI(title="Rate Limiter API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

AlgorithmName = Literal["token_bucket", "fixed_window", "sliding_window"]

# Build limiter instances — Redis-backed if REDIS_URL is set, in-memory otherwise.
# Swapping backends does not change the RateLimiter interface callers use.
_redis_url = os.environ.get("REDIS_URL")
if _redis_url:  # pragma: no cover
    import redis as _redis_lib
    _rc = _redis_lib.Redis.from_url(_redis_url, decode_responses=False)
    _token_bucket: RateLimiter = RedisTokenBucket(_rc, capacity=10, refill_rate=1.0)
    _fixed_window: RateLimiter = RedisFixedWindow(_rc, max_requests=10, window_seconds=60)
    _sliding_window: RateLimiter = RedisSlidingWindow(_rc, max_requests=10, window_seconds=60)
    _backend_label = "redis"
else:
    _token_bucket = TokenBucket(capacity=10, refill_rate=1.0)
    _fixed_window = FixedWindow(max_requests=10, window_seconds=60)
    _sliding_window = SlidingWindow(max_requests=10, window_seconds=60)
    _backend_label = "memory"


class CheckRequest(BaseModel):
    key: str
    algorithm: AlgorithmName


class ResetRequest(BaseModel):
    key: str
    algorithm: AlgorithmName


class CheckResponse(BaseModel):
    allowed: bool
    remaining: int
    algorithm: str
    key: str


class ResetResponse(BaseModel):
    reset: bool
    key: str


class HealthResponse(BaseModel):
    status: str
    backend: str


class TestResult(BaseModel):
    name: str
    status: str  # "passed" | "failed" | "error"
    message: str | None = None


class TestRunResponse(BaseModel):
    passed: int
    failed: int
    errors: int
    duration: float
    results: list[TestResult]


class StateResponse(BaseModel):
    remaining: int
    capacity: int
    algorithm: str
    key: str
    window_elapsed: float | None = None
    window_total: float | None = None


def get_token_bucket() -> RateLimiter:
    return _token_bucket


def get_fixed_window() -> RateLimiter:
    return _fixed_window


def get_sliding_window() -> RateLimiter:
    return _sliding_window


def _resolve_limiter(
    algorithm: AlgorithmName,
    token_bucket: RateLimiter,
    fixed_window: RateLimiter,
    sliding_window: RateLimiter,
) -> RateLimiter:
    if algorithm == "token_bucket":
        return token_bucket
    if algorithm == "fixed_window":
        return fixed_window
    return sliding_window


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/check", response_model=CheckResponse)
def check(
    body: CheckRequest,
    token_bucket: RateLimiter = Depends(get_token_bucket),
    fixed_window: RateLimiter = Depends(get_fixed_window),
    sliding_window: RateLimiter = Depends(get_sliding_window),
) -> CheckResponse:
    """Check whether a request is allowed and consume a token."""
    limiter = _resolve_limiter(body.algorithm, token_bucket, fixed_window, sliding_window)
    allowed, remaining = limiter.allow(body.key)
    return CheckResponse(
        allowed=allowed,
        remaining=remaining,
        algorithm=body.algorithm,
        key=body.key,
    )


@app.post("/reset", response_model=ResetResponse)
def reset(
    body: ResetRequest,
    token_bucket: RateLimiter = Depends(get_token_bucket),
    fixed_window: RateLimiter = Depends(get_fixed_window),
    sliding_window: RateLimiter = Depends(get_sliding_window),
) -> ResetResponse:
    """Reset rate limit state for a key."""
    limiter = _resolve_limiter(body.algorithm, token_bucket, fixed_window, sliding_window)
    limiter.reset(body.key)
    return ResetResponse(reset=True, key=body.key)


@app.get("/state/{algorithm}/{key}", response_model=StateResponse)
def state(
    algorithm: AlgorithmName,
    key: str,
    token_bucket: RateLimiter = Depends(get_token_bucket),
    fixed_window: RateLimiter = Depends(get_fixed_window),
    sliding_window: RateLimiter = Depends(get_sliding_window),
) -> StateResponse:
    """Current quota state for a key — polled by the dashboard."""
    if algorithm == "token_bucket":
        assert isinstance(token_bucket, (TokenBucket, RedisTokenBucket))
        return StateResponse(
            remaining=token_bucket.remaining(key),
            capacity=token_bucket.capacity,
            algorithm=algorithm,
            key=key,
        )
    if algorithm == "fixed_window":
        assert isinstance(fixed_window, (FixedWindow, RedisFixedWindow))
        remaining, elapsed, total = fixed_window.window_state(key)
        return StateResponse(
            remaining=remaining,
            capacity=fixed_window.max_requests,
            algorithm=algorithm,
            key=key,
            window_elapsed=elapsed,
            window_total=total,
        )
    # sliding_window
    assert isinstance(sliding_window, (SlidingWindow, RedisSlidingWindow))
    remaining, oldest_age, total = sliding_window.window_state(key)
    return StateResponse(
        remaining=remaining,
        capacity=sliding_window.max_requests,
        algorithm=algorithm,
        key=key,
        window_elapsed=oldest_age,
        window_total=total,
    )


@app.get("/tests/run")
def run_tests() -> TestRunResponse:
    """Run the pytest suite and return per-test results."""
    project_root = Path(__file__).parent.parent
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--no-header", "--tb=short",
         "--override-ini=addopts="],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # merge — avoids Windows pipe deadlock
        cwd=project_root,
        timeout=60,
    )
    output = proc.stdout.decode("utf-8", errors="replace")

    results: list[TestResult] = []
    line_re = re.compile(
        r"^(tests/[\w/]+\.py::[\w:]+)\s+(PASSED|FAILED|ERROR)", re.MULTILINE
    )
    for m in line_re.finditer(output):
        results.append(TestResult(
            name=m.group(1),
            status=m.group(2).lower(),
        ))

    fail_re = re.compile(
        r"FAILED (tests/[\w/]+\.py::[\w:]+)[^\n]*\n(.*)(?=\nFAILED |\n={3}|\Z)",
        re.DOTALL,
    )
    fail_msgs: dict[str, str] = {
        m.group(1): m.group(2).strip() for m in fail_re.finditer(output)
    }
    for r in results:
        if r.status == "failed" and r.name in fail_msgs:
            r.message = fail_msgs[r.name]

    passed = sum(1 for r in results if r.status == "passed")
    failed = sum(1 for r in results if r.status == "failed")
    errors = sum(1 for r in results if r.status == "error")

    duration = 0.0
    dur_m = re.search(r"in (\d+\.\d+)s", output)
    if dur_m:
        duration = float(dur_m.group(1))

    return TestRunResponse(
        passed=passed, failed=failed, errors=errors,
        duration=duration, results=results,
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", backend=_backend_label)
