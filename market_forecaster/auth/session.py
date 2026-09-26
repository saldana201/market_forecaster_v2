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



def _restore_requested_plan(
    state: MutableMapping,
    user: AuthUser,
    *,
    force: bool = False,
) -> None:
    requested = str(user.requested_plan or "").strip().lower()
    if requested not in {"standard", "pro"}:
        return

    current = str(state.get("requested_plan") or "").strip().lower()
    if not force and current in {"standard", "pro"}:
        return

    state["requested_plan"] = requested
    # account_plan_choice is a Streamlit widget key. Authentication can finish
    # after that widget has already been instantiated on the current run, so
    # never mutate it here. Queue the visible selection for the next render.
    state["account_plan_choice_pending"] = requested.title()


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
    restore_requested_plan_force: bool = True,
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
    _restore_requested_plan(
        state,
        result.user,
        force=restore_requested_plan_force,
    )
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
    except InvalidToken:
        refresh_token = str(auth.get("refresh_token") or "").strip()
        if not refresh_token:
            clear_authenticated_session(state)
            raise

        result = provider.refresh_session(refresh_token)
        if result.tokens is None or not result.tokens.access_token:
            clear_authenticated_session(state)
            raise InvalidToken("Authentication refresh did not return an active session.")

        identity = establish_authenticated_session(
            state,
            result,
            provider_name=provider.name,
            plan=plan,
            restore_requested_plan_force=False,
        )
        return identity
    except AuthProviderError:
        # Provider/network outages should not silently destroy a valid local
        # session. Let the caller surface a temporary verification warning.
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
    _restore_requested_plan(state, user, force=False)
    return identity


def clear_authenticated_session(state: MutableMapping) -> AppIdentity:
    ensure_demo_session(state)
    state.pop(AUTH_SESSION_KEY, None)
    state.pop(AUTH_PROFILE_KEY, None)
    state.pop("_preferences_loaded_for", None)
    state.pop("user_preferences", None)
    state.pop("account_default_ticker", None)
    state.pop("account_timezone", None)
    state.pop("simple_forecast_contract", None)
    state.pop("billing_checkout_url", None)
    state.pop("billing_checkout_plan", None)
    state.pop("_browser_session_handle", None)
    state.pop("_browser_session_refresh_hash", None)
    identity = new_demo_identity_for_session(str(state[DEMO_SESSION_KEY]["session_id"]))
    state[IDENTITY_SESSION_KEY] = identity.to_dict()
    return identity


def auth_profile(state: MutableMapping) -> dict:
    profile = state.get(AUTH_PROFILE_KEY)
    return profile if isinstance(profile, dict) else {}
