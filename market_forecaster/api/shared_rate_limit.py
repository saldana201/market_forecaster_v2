"""Shared multi-instance API rate limiting backed by Supabase Postgres."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from urllib import error, request


class SharedRateLimitError(RuntimeError):
    """Raised when the shared rate-limit backend cannot be used."""


@dataclass(frozen=True)
class SharedRateLimitResult:
    allowed: bool
    request_count: int
    retry_after_seconds: int


def _supabase_url() -> str:
    return str(
        os.getenv("MARKET_FORECASTER_SUPABASE_URL")
        or os.getenv("SUPABASE_URL")
        or ""
    ).strip().rstrip("/")


def _service_role_key() -> str:
    return str(
        os.getenv("MARKET_FORECASTER_SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    ).strip()


def _hash_secret() -> str:
    return str(
        os.getenv("MARKET_FORECASTER_RATE_LIMIT_HASH_SECRET")
        or os.getenv("MARKET_FORECASTER_API_KEY")
        or ""
    ).strip()


def shared_rate_limit_configuration_status(enabled: bool) -> tuple[bool, str]:
    if not enabled:
        return False, "Shared API rate limiting is disabled."
    if not _supabase_url():
        return False, "Supabase URL is not configured."
    if not _service_role_key():
        return False, "Supabase service-role key is not configured on the API host."
    if not _hash_secret():
        return False, "Rate-limit hash secret/API key is not configured."
    return True, "ready"


class SharedRateLimiter:
    def __init__(
        self,
        *,
        requests: int,
        window_seconds: int,
        enabled: bool,
        timeout_seconds: float = 2.0,
    ):
        self.requests = int(requests)
        self.window_seconds = int(window_seconds)
        self.enabled = bool(enabled)
        self.timeout_seconds = float(timeout_seconds)

    def configured(self) -> tuple[bool, str]:
        return shared_rate_limit_configuration_status(self.enabled)

    def _bucket_key(self, client_key: str) -> str:
        secret = _hash_secret()
        if not secret:
            raise SharedRateLimitError("Rate-limit hash secret is not configured.")
        return hmac.new(
            secret.encode("utf-8"),
            str(client_key or "unknown").encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def consume(self, client_key: str) -> SharedRateLimitResult:
        ready, reason = self.configured()
        if not ready:
            raise SharedRateLimitError(reason)

        endpoint = (
            f"{_supabase_url()}/rest/v1/rpc/"
            "consume_market_forecaster_rate_limit"
        )
        payload = json.dumps(
            {
                "p_bucket_key": self._bucket_key(client_key),
                "p_limit": self.requests,
                "p_window_seconds": self.window_seconds,
            }
        ).encode("utf-8")
        service_key = _service_role_key()
        req = request.Request(
            endpoint,
            data=payload,
            method="POST",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise SharedRateLimitError(
                f"Shared rate limiter rejected request ({exc.code}): {body}"
            ) from exc
        except error.URLError as exc:
            raise SharedRateLimitError(
                f"Shared rate limiter unavailable: {exc.reason}"
            ) from exc

        try:
            parsed = json.loads(raw)
            row = parsed[0] if isinstance(parsed, list) and parsed else parsed
            return SharedRateLimitResult(
                allowed=bool(row["allowed"]),
                request_count=int(row["request_count"]),
                retry_after_seconds=max(0, int(row["retry_after_seconds"])),
            )
        except Exception as exc:
            raise SharedRateLimitError(
                "Shared rate limiter returned an unexpected response."
            ) from exc
