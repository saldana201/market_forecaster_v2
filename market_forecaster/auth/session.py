"""Authenticated Streamlit session bridge.

Security identity is derived from a verified provider subject. A caller-supplied
user_id is never accepted.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import MutableMapping
from uuid import NAMESPACE_URL, uuid5

from market_forecaster.auth.provider import AuthProvider, AuthProviderError, AuthResult, AuthUser, InvalidToken
from market_forecaster.core.session_identity import (
    DEMO_SESSION_KEY,
    IDENTITY_SESSION_KEY,
    AppIdentity,
    ensure_demo_session,
    new_demo_identity_for_session,
)


AUTH_SESSION_KEY = "auth_session"
AUTH_PROFILE_KEY = "auth_profile"


def stable_internal_user_id(provider_name: str, subject: str) -> str:
    """Create a stable application UUID without using email as the key."""
    source = f"market-forecaster:{provider_name.strip().lower()}:{subject.strip()}"
    return str(uuid5(NAMESPACE_URL, source))


def identity_from_verified_user(
    user: AuthUser,
    *,
    provider_name: str,
    session_id: str,
    plan: str = "standard",
) -> AppIdentity:
    return AppIdentity(
        user_id=stable_internal_user_id(provider_name, user.subject),
        session_id=session_id,
        authenticated=True,
        plan=plan,
        subscription_status="bootstrap",
        is_admin=False,
        auth_provider=provider_name,
        auth_subject=user.subject,
    )


def establish_authenticated_session(
    state: MutableMapping,
    result: AuthResult,
    *,
    provider_name: str,
    plan: str = "standard",
) -> AppIdentity:
    if result.tokens is None or not result.tokens.access_token:
        raise InvalidToken("Authentication completed without an active access token.")

    demo = ensure_demo_session(state)
    identity = identity_from_verified_user(
        result.user,
        provider_name=provider_name,
        session_id=str(demo["session_id"]),
        plan=plan,
    )
    state[AUTH_SESSION_KEY] = {
        "provider": provider_name,
        "access_token": result.tokens.access_token,
        "refresh_token": result.tokens.refresh_token,
        "expires_in": result.tokens.expires_in,
        "authenticated_at": datetime.now(timezone.utc).isoformat(),
    }
    state[AUTH_PROFILE_KEY] = {
        "email": result.user.email,
        "display_name": result.user.display_name,
        "email_confirmed": result.user.email_confirmed,
    }
    state[IDENTITY_SESSION_KEY] = identity.to_dict()
    return identity


def sync_authenticated_identity(
    state: MutableMapping,
    provider: AuthProvider,
    *,
    plan: str = "standard",
) -> AppIdentity:
    ensure_demo_session(state)
    auth = state.get(AUTH_SESSION_KEY)
    if not isinstance(auth, dict) or not auth.get("access_token"):
        return new_demo_identity_for_session(str(state[DEMO_SESSION_KEY]["session_id"]))

    try:
        user = provider.verify_token(str(auth["access_token"]))
    except (InvalidToken, AuthProviderError):
        clear_authenticated_session(state)
        raise

    identity = identity_from_verified_user(
        user,
        provider_name=provider.name,
        session_id=str(state[DEMO_SESSION_KEY]["session_id"]),
        plan=plan,
    )
    state[AUTH_PROFILE_KEY] = {
        "email": user.email,
        "display_name": user.display_name,
        "email_confirmed": user.email_confirmed,
    }
    state[IDENTITY_SESSION_KEY] = identity.to_dict()
    return identity


def clear_authenticated_session(state: MutableMapping) -> AppIdentity:
    ensure_demo_session(state)
    state.pop(AUTH_SESSION_KEY, None)
    state.pop(AUTH_PROFILE_KEY, None)
    identity = new_demo_identity_for_session(str(state[DEMO_SESSION_KEY]["session_id"]))
    state[IDENTITY_SESSION_KEY] = identity.to_dict()
    return identity


def auth_profile(state: MutableMapping) -> dict:
    profile = state.get(AUTH_PROFILE_KEY)
    return profile if isinstance(profile, dict) else {}
