"""Request IDs, structured access logs, and lightweight abuse protection."""

from __future__ import annotations

import asyncio
import hashlib
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
            principal = getattr(request.state, "api_principal", None)
            logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                        "api_principal_type": (
                            principal.get("type")
                            if isinstance(principal, dict)
                            else None
                        ),
                    },
                    separators=(",", ":"),
                )
            )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Shared limiter with an in-process fallback.

    Every API request is rate-limited by source IP. Customer Pro API keys also
    receive a second independent bucket keyed by a one-way SHA-256 fingerprint
    of the presented key, so a single key cannot bypass limits by moving across
    client networks. Raw API keys are never stored in limiter state.
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

    def _client_keys(self, request: Request) -> list[str]:
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        client = forwarded or (request.client.host if request.client else "unknown")
        keys = [f"ip:{client}"]

        presented = str(request.headers.get("x-api-key") or "").strip()
        if presented.startswith("mfk_"):
            digest = hashlib.sha256(presented.encode("utf-8")).hexdigest()
            keys.append(f"customer_api:{digest}")
        return keys

    def _rate_limit_response(
        self,
        request: Request,
        *,
        retry_after_seconds: int,
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded", "request_id": request_id},
            headers={"Retry-After": str(max(1, int(retry_after_seconds)))},
        )

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/v1/") or request.url.path in {
            "/api/v1/health",
            "/api/v1/ready",
        }:
            return await call_next(request)

        client_keys = self._client_keys(request)

        if self.shared_limiter is not None:
            ready, _reason = self.shared_limiter.configured()
            if ready:
                try:
                    for client_key in client_keys:
                        result = await asyncio.to_thread(
                            self.shared_limiter.consume,
                            client_key,
                        )
                        if not result.allowed:
                            return self._rate_limit_response(
                                request,
                                retry_after_seconds=result.retry_after_seconds,
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
            buckets: list[deque[float]] = []
            for client_key in client_keys:
                bucket = self._hits[client_key]
                while bucket and bucket[0] < cutoff:
                    bucket.popleft()
                buckets.append(bucket)

            if any(len(bucket) >= self.requests for bucket in buckets):
                return self._rate_limit_response(
                    request,
                    retry_after_seconds=self.window_seconds,
                )

            for bucket in buckets:
                bucket.append(now)

        return await call_next(request)
