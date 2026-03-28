"""FastAPI wrapper for the rate limiter library.

Thin HTTP layer only — no business logic lives here. All rate limiting
decisions happen inside app/.
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

# Shared instances — created once at startup
_token_bucket = TokenBucket(capacity=10, refill_rate=1.0)
_fixed_window = FixedWindow(max_requests=10, window_seconds=60)

AlgorithmName = Literal["token_bucket", "fixed_window"]


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


class StateResponse(BaseModel):
    remaining: int
    capacity: int
    algorithm: str
    key: str
    window_elapsed: float | None = None
    window_total: float | None = None


def get_token_bucket() -> TokenBucket:
    return _token_bucket


def get_fixed_window() -> FixedWindow:
    return _fixed_window


def _resolve_limiter(
    algorithm: AlgorithmName,
    token_bucket: TokenBucket,
    fixed_window: FixedWindow,
) -> RateLimiter:
    if algorithm == "token_bucket":
        return token_bucket
    return fixed_window


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/check", response_model=CheckResponse)
def check(
    body: CheckRequest,
    token_bucket: TokenBucket = Depends(get_token_bucket),
    fixed_window: FixedWindow = Depends(get_fixed_window),
) -> CheckResponse:
    """Check whether a request is allowed and consume a token."""
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
    """Reset rate limit state for a key."""
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
    """Current quota state for a key — polled by the dashboard."""
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
    return HealthResponse(status="ok")
