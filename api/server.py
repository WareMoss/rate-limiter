"""FastAPI HTTP wrapper around the rate limiter library.

This module contains zero business logic. It translates HTTP requests into
calls on RateLimiter instances and returns structured JSON responses.
All rate limiting decisions are made inside the library (app/).

The /check endpoint uses RateLimiter.allow() rather than calling is_allowed()
and remaining() separately — both values come from a single atomic operation
so the remaining count in the response is never stale.
"""

from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.base import RateLimiter
from app.fixed_window import FixedWindow
from app.token_bucket import TokenBucket

STATIC_DIR = Path(__file__).parent.parent / "static"

app = FastAPI(title="Rate Limiter API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Single shared instances — instantiated once at startup with sensible defaults.
_token_bucket: TokenBucket = TokenBucket(capacity=10, refill_rate=1.0)
_fixed_window: FixedWindow = FixedWindow(max_requests=10, window_seconds=60)

AlgorithmName = Literal["token_bucket", "fixed_window"]


# ── Pydantic models ───────────────────────────────────────────────────────────


class CheckRequest(BaseModel):
    """Request body for the /check endpoint."""

    key: str
    algorithm: AlgorithmName


class ResetRequest(BaseModel):
    """Request body for the /reset endpoint."""

    key: str
    algorithm: AlgorithmName


class CheckResponse(BaseModel):
    """Response body for the /check endpoint."""

    allowed: bool
    remaining: int
    algorithm: str
    key: str


class ResetResponse(BaseModel):
    """Response body for the /reset endpoint."""

    reset: bool
    key: str


class HealthResponse(BaseModel):
    """Response body for the /health endpoint."""

    status: str


class StateResponse(BaseModel):
    """Response body for the /state endpoint (used by the dashboard)."""

    remaining: int
    capacity: int
    algorithm: str
    key: str
    window_elapsed: float | None = None
    window_total: float | None = None


# ── Dependencies ──────────────────────────────────────────────────────────────


def get_token_bucket() -> TokenBucket:
    """Dependency that provides the shared TokenBucket instance."""
    return _token_bucket


def get_fixed_window() -> FixedWindow:
    """Dependency that provides the shared FixedWindow instance."""
    return _fixed_window


def _resolve_limiter(
    algorithm: AlgorithmName,
    token_bucket: TokenBucket,
    fixed_window: FixedWindow,
) -> RateLimiter:
    """Return the RateLimiter instance that corresponds to *algorithm*."""
    if algorithm == "token_bucket":
        return token_bucket
    return fixed_window


# ── Routes ────────────────────────────────────────────────────────────────────


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the visualisation dashboard."""
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/check", response_model=CheckResponse)
def check(
    body: CheckRequest,
    token_bucket: TokenBucket = Depends(get_token_bucket),
    fixed_window: FixedWindow = Depends(get_fixed_window),
) -> CheckResponse:
    """Check whether a request is allowed under the chosen algorithm.

    Uses RateLimiter.allow() so that the allowed flag and the remaining count
    are derived from the same atomic operation — no race window between them.
    """
    limiter = _resolve_limiter(body.algorithm, token_bucket, fixed_window)
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
    token_bucket: TokenBucket = Depends(get_token_bucket),
    fixed_window: FixedWindow = Depends(get_fixed_window),
) -> ResetResponse:
    """Reset the rate limit state for a given key and algorithm."""
    limiter = _resolve_limiter(body.algorithm, token_bucket, fixed_window)
    limiter.reset(body.key)
    return ResetResponse(reset=True, key=body.key)


@app.get("/state/{algorithm}/{key}", response_model=StateResponse)
def state(
    algorithm: AlgorithmName,
    key: str,
    token_bucket: TokenBucket = Depends(get_token_bucket),
    fixed_window: FixedWindow = Depends(get_fixed_window),
) -> StateResponse:
    """Return current quota state for a key — used by the live dashboard.

    For FixedWindow the response includes window_elapsed and window_total so
    the frontend can render a countdown timer.  Both values come from a single
    atomic call so they are mutually consistent.
    """
    if algorithm == "token_bucket":
        return StateResponse(
            remaining=token_bucket.remaining(key),
            capacity=token_bucket.capacity,
            algorithm=algorithm,
            key=key,
        )
    remaining, elapsed, total = fixed_window.window_state(key)
    return StateResponse(
        remaining=remaining,
        capacity=fixed_window.max_requests,
        algorithm=algorithm,
        key=key,
        window_elapsed=elapsed,
        window_total=total,
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe — returns 200 OK when the server is running."""
    return HealthResponse(status="ok")
