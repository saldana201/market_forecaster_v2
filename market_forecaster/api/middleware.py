"""Request IDs, structured access logs, and lightweight abuse protection."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from market_forecaster.api.shared_rate_limit import (
    SharedRateLimitError,
    SharedRateLimiter,
)

logger = logging.getLogger("market_forecaster.api")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["x-request-id"] = request_id
            return response
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                    },
                    separators=(",", ":"),
                )
            )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Shared limiter with an in-process fallback.

    When the shared Supabase limiter is configured, all API instances consume
    the same fixed-window bucket. If that backend is temporarily unavailable,
    the existing process-local limiter remains an availability-safe fallback.
    """

    def __init__(
        self,
        app,
        *,
        requests: int,
        window_seconds: int,
        shared_limiter: SharedRateLimiter | None = None,
    ):
        super().__init__(app)
        self.requests = requests
        self.window_seconds = window_seconds
        self.shared_limiter = shared_limiter
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/v1/") or request.url.path in {
            "/api/v1/health",
            "/api/v1/ready",
        }:
            return await call_next(request)

        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        client = forwarded or (request.client.host if request.client else "unknown")

        if self.shared_limiter is not None:
            ready, _reason = self.shared_limiter.configured()
            if ready:
                try:
                    result = await asyncio.to_thread(
                        self.shared_limiter.consume,
                        client,
                    )
                    if not result.allowed:
                        request_id = getattr(
                            request.state,
                            "request_id",
                            uuid.uuid4().hex,
                        )
                        return JSONResponse(
                            status_code=429,
                            content={
                                "detail": "Rate limit exceeded",
                                "request_id": request_id,
                            },
                            headers={
                                "Retry-After": str(
                                    max(1, result.retry_after_seconds)
                                )
                            },
                        )
                    return await call_next(request)
                except SharedRateLimitError as exc:
                    logger.warning(
                        "shared_rate_limit_fallback reason=%s",
                        exc,
                    )

        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            bucket = self._hits[client]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.requests:
                request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded", "request_id": request_id},
                    headers={"Retry-After": str(self.window_seconds)},
                )
            bucket.append(now)

        return await call_next(request)
