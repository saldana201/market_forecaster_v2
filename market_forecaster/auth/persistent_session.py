"""Persistent browser authentication orchestration."""
from __future__ import annotations

import hashlib
from typing import MutableMapping

from market_forecaster.auth.browser_session_store import (
    BrowserSessionError,
    create_browser_session,
    load_browser_session,
    revoke_browser_session,
    rotate_browser_refresh_token,
)
from market_forecaster.auth.provider import AuthProvider, AuthResult, InvalidToken
from market_forecaster.auth.session import (
    AUTH_SESSION_KEY,
    establish_authenticated_session,
)
from market_forecaster.core.session_identity import AppIdentity
from market_forecaster.ui.browser_session import (
    queue_browser_session_clear,
    queue_browser_session_set,
)


BROWSER_SESSION_HANDLE_KEY = "_browser_session_handle"
BROWSER_SESSION_REFRESH_HASH_KEY = "_browser_session_refresh_hash"


def _token_hash(value: str | None) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def issue_persistent_browser_session(
    state: MutableMapping,
    result: AuthResult,
    *,
    user_agent: str,
) -> str | None:
    if result.tokens is None or not result.tokens.refresh_token:
        return None

    handle = create_browser_session(
        auth_subject=result.user.subject,
        refresh_token=result.tokens.refresh_token,
        user_agent=user_agent,
    )
    state[BROWSER_SESSION_HANDLE_KEY] = handle
    state[BROWSER_SESSION_REFRESH_HASH_KEY] = _token_hash(
        result.tokens.refresh_token
    )
    queue_browser_session_set(state, handle)
    return handle


def restore_persistent_browser_session(
    state: MutableMapping,
    provider: AuthProvider,
    *,
    handle: str,
    user_agent: str,
    plan: str = "standard",
) -> AppIdentity | None:
    stored = load_browser_session(handle=handle, user_agent=user_agent)
    if stored is None:
        queue_browser_session_clear(state)
        return None

    result = provider.refresh_session(stored.refresh_token)
    if result.tokens is None or not result.tokens.refresh_token:
        revoke_browser_session(handle)
        queue_browser_session_clear(state)
        raise InvalidToken("Persistent browser session did not refresh.")

    if result.user.subject != stored.auth_subject:
        revoke_browser_session(handle)
        queue_browser_session_clear(state)
        raise InvalidToken("Persistent browser session identity mismatch.")

    identity = establish_authenticated_session(
        state,
        result,
        provider_name=provider.name,
        plan=plan,
    )
    state[BROWSER_SESSION_HANDLE_KEY] = handle
    state[BROWSER_SESSION_REFRESH_HASH_KEY] = _token_hash(
        result.tokens.refresh_token
    )
    rotate_browser_refresh_token(
        handle=handle,
        refresh_token=result.tokens.refresh_token,
    )
    return identity


def sync_persistent_browser_refresh_token(
    state: MutableMapping,
) -> None:
    handle = str(state.get(BROWSER_SESSION_HANDLE_KEY) or "")
    auth = state.get(AUTH_SESSION_KEY)
    if not handle or not isinstance(auth, dict):
        return

    refresh_token = str(auth.get("refresh_token") or "")
    if not refresh_token:
        return

    new_hash = _token_hash(refresh_token)
    if new_hash == state.get(BROWSER_SESSION_REFRESH_HASH_KEY):
        return

    rotate_browser_refresh_token(
        handle=handle,
        refresh_token=refresh_token,
    )
    state[BROWSER_SESSION_REFRESH_HASH_KEY] = new_hash


def revoke_persistent_browser_session(state: MutableMapping) -> None:
    handle = str(state.get(BROWSER_SESSION_HANDLE_KEY) or "")
    if handle:
        try:
            revoke_browser_session(handle)
        except BrowserSessionError:
            pass
    state.pop(BROWSER_SESSION_HANDLE_KEY, None)
    state.pop(BROWSER_SESSION_REFRESH_HASH_KEY, None)
    queue_browser_session_clear(state)
