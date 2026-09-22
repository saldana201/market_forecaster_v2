"""Authenticated account endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from market_forecaster.api.user_auth import require_user_identity
from market_forecaster.core.session_identity import AppIdentity

router = APIRouter()


@router.get("/account/me")
async def account_me(identity: AppIdentity = Depends(require_user_identity)):
    return {
        "user_id": identity.user_id,
        "authenticated": identity.authenticated,
        "plan": identity.plan,
        "subscription_status": identity.subscription_status,
        "auth_provider": identity.auth_provider,
    }
