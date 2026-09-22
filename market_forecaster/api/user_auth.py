"""Bearer-token authentication for user-scoped API routes."""
from __future__ import annotations

import uuid

from fastapi import HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from market_forecaster.auth.factory import get_auth_provider
from market_forecaster.auth.provider import AuthConfigurationError, AuthProviderError, InvalidToken
from market_forecaster.auth.session import identity_from_verified_user
from market_forecaster.core.session_identity import AppIdentity

_bearer = HTTPBearer(auto_error=False)


async def require_user_identity(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> AppIdentity:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    try:
        provider = get_auth_provider()
        user = provider.verify_token(credentials.credentials)
    except AuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account authentication is not configured",
        ) from exc
    except (InvalidToken, AuthProviderError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired bearer token",
        ) from exc

    request_id = getattr(request.state, "request_id", None) or uuid.uuid4().hex
    return identity_from_verified_user(
        user,
        provider_name=provider.name,
        session_id=str(request_id),
        plan="standard",
    )
