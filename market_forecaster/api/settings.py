"""Environment-backed API settings with production fail-fast checks."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class APISettings:
    environment: str
    api_key: str | None
    allowed_origins: tuple[str, ...]
    allow_credentials: bool
    rate_limit_requests: int
    rate_limit_window_seconds: int
    shared_rate_limit_enabled: bool

    @property
    def production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_key)

    def validate(self) -> None:
        if self.production and not self.api_key:
            raise RuntimeError("MARKET_FORECASTER_API_KEY is required in production")
        if self.production and not self.allowed_origins:
            raise RuntimeError("MARKET_FORECASTER_ALLOWED_ORIGINS is required in production")
        if "*" in self.allowed_origins and self.allow_credentials:
            raise RuntimeError("Wildcard CORS cannot be used with credentials")


def load_settings() -> APISettings:
    origins = tuple(
        item.strip()
        for item in os.getenv(
            "MARKET_FORECASTER_ALLOWED_ORIGINS",
            "http://localhost:8501,http://127.0.0.1:8501",
        ).split(",")
        if item.strip()
    )
    settings = APISettings(
        environment=os.getenv("MARKET_FORECASTER_ENV", "development"),
        api_key=os.getenv("MARKET_FORECASTER_API_KEY") or None,
        allowed_origins=origins,
        allow_credentials=_bool("MARKET_FORECASTER_ALLOW_CREDENTIALS", False),
        rate_limit_requests=max(1, _int("MARKET_FORECASTER_RATE_LIMIT_REQUESTS", 30)),
        rate_limit_window_seconds=max(1, _int("MARKET_FORECASTER_RATE_LIMIT_WINDOW_SECONDS", 60)),
        shared_rate_limit_enabled=_bool(
            "MARKET_FORECASTER_SHARED_RATE_LIMIT_ENABLED",
            False,
        ),
    )
    settings.validate()
    return settings
