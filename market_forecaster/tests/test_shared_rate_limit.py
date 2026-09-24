from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from market_forecaster.api.middleware import RateLimitMiddleware
from market_forecaster.api.shared_rate_limit import (
    SharedRateLimitError,
    SharedRateLimiter,
    SharedRateLimitResult,
)


def test_shared_rate_limit_hashes_client_identifier_before_rpc(monkeypatch):
    captured = {}

    monkeypatch.setenv(
        "MARKET_FORECASTER_SUPABASE_URL",
        "https://example.supabase.co",
    )
    monkeypatch.setenv(
        "MARKET_FORECASTER_SUPABASE_SERVICE_ROLE_KEY",
        "service-role-test",
    )
    monkeypatch.setenv(
        "MARKET_FORECASTER_RATE_LIMIT_HASH_SECRET",
        "rate-limit-secret",
    )

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                [{
                    "allowed": True,
                    "request_count": 1,
                    "retry_after_seconds": 60,
                }]
            ).encode("utf-8")

    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["url"] = req.full_url
        captured["apikey"] = req.headers["Apikey"]
        captured["authorization"] = req.headers["Authorization"]
        return FakeResponse()

    monkeypatch.setattr(
        "market_forecaster.api.shared_rate_limit.request.urlopen",
        fake_urlopen,
    )

    limiter = SharedRateLimiter(
        requests=30,
        window_seconds=60,
        enabled=True,
    )
    raw_client = "203.0.113.5"
    result = limiter.consume(raw_client)

    expected = hmac.new(
        b"rate-limit-secret",
        raw_client.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    assert result.allowed is True
    assert captured["body"]["p_bucket_key"] == expected
    assert raw_client not in json.dumps(captured["body"])
    assert captured["apikey"] == "service-role-test"
    assert captured["authorization"] == "Bearer service-role-test"
    assert "consume_market_forecaster_rate_limit" in captured["url"]


class _BlockingSharedLimiter:
    def configured(self):
        return True, "ready"

    def consume(self, client_key):
        return SharedRateLimitResult(
            allowed=False,
            request_count=31,
            retry_after_seconds=42,
        )


class _FailingSharedLimiter:
    def configured(self):
        return True, "ready"

    def consume(self, client_key):
        raise SharedRateLimitError("temporary shared backend outage")


def _app_with_limiter(shared_limiter, *, requests=2):
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        requests=requests,
        window_seconds=60,
        shared_limiter=shared_limiter,
    )

    @app.get("/api/v1/example")
    async def example():
        return {"ok": True}

    return app


def test_middleware_uses_shared_retry_after():
    client = TestClient(_app_with_limiter(_BlockingSharedLimiter()))

    response = client.get("/api/v1/example")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "42"


def test_middleware_falls_back_locally_if_shared_backend_fails():
    client = TestClient(_app_with_limiter(_FailingSharedLimiter(), requests=1))

    first = client.get("/api/v1/example")
    second = client.get("/api/v1/example")

    assert first.status_code == 200
    assert second.status_code == 429
