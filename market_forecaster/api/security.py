"""API authentication for internal and Pro customer API keys."""

from __future__ import annotations

import asyncio
import hmac

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from market_forecaster.api.settings import load_settings
from market_forecaster.services.api_keys import (
    APIKeyStoreError,
    InvalidCustomerAPIKey,
    consume_customer_api_request,
    validate_customer_api_key,
)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    request: Request,
    api_key: str | None = Security(_api_key_header),
) -> None:
    settings = load_settings()
    presented = str(api_key or "").strip()

    # Preserve the existing server/internal integration key as a trusted path.
    if (
        presented
        and settings.api_key
        and hmac.compare_digest(presented, settings.api_key)
    ):
        request.state.api_principal = {
            "type": "internal",
            "plan": "internal",
        }
        return

    # Pro customer keys are individually issued, revocable, stored only as
    # hashes, and re-check subscription authority on every authenticated call.
    if presented.startswith("mfk_"):
        try:
            principal = await asyncio.to_thread(
                validate_customer_api_key,
                presented,
            )
        except InvalidCustomerAPIKey as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or inactive API key",
            ) from exc
        except APIKeyStoreError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Customer API key authorization is temporarily unavailable",
            ) from exc

        try:
            usage = await asyncio.to_thread(
                consume_customer_api_request,
                principal,
                monthly_limit=settings.pro_api_monthly_requests,
            )
        except APIKeyStoreError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Customer API usage metering is temporarily unavailable",
            ) from exc

        if not usage.allowed:
            request.state.api_usage = usage
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Monthly Pro API request quota exceeded",
            )

        request.state.api_usage = usage
        request.state.api_principal = {
            "type": "customer",
            "user_id": principal.user_id,
            "key_id": principal.key_id,
            "key_prefix": principal.key_prefix,
            "plan": principal.plan,
            "subscription_status": principal.subscription_status,
        }
        return

    # Development keeps the pre-existing optional-auth behavior. Production
    # settings already fail fast when the internal API key is not configured.
    if not settings.auth_enabled:
        request.state.api_principal = {
            "type": "development",
            "plan": "development",
        }
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API key",
    )
