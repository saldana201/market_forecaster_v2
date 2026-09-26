from __future__ import annotations

import hashlib

from market_forecaster.auth import browser_session_store as store
from market_forecaster.auth.persistent_session import (
    BROWSER_SESSION_HANDLE_KEY,
    ensure_persistent_browser_session,
    restore_persistent_browser_session,
)
from market_forecaster.auth.provider import AuthResult, AuthTokens, AuthUser
from market_forecaster.core.session_identity import resolve_identity


class RefreshingProvider:
    name = "fake"

    def refresh_session(self, refresh_token: str) -> AuthResult:
        assert refresh_token == "refresh-old"
        return AuthResult(
            user=AuthUser(
                subject="11111111-1111-4111-8111-111111111111",
                email="user@example.com",
                display_name="User",
                email_confirmed=True,
                requested_plan="pro",
            ),
            tokens=AuthTokens(
                access_token="access-new",
                refresh_token="refresh-new",
                expires_in=3600,
            ),
        )


def test_create_browser_session_stores_hash_and_encrypted_refresh_token(monkeypatch):
    monkeypatch.setenv("MARKET_FORECASTER_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv(
        "MARKET_FORECASTER_SUPABASE_SERVICE_ROLE_KEY",
        "service-role-super-secret",
    )
    captured = {}

    def fake_request_rows(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(store, "_request_rows", fake_request_rows)

    handle = store.create_browser_session(
        auth_subject="11111111-1111-4111-8111-111111111111",
        refresh_token="refresh-token-secret",
        user_agent="Browser/1.0",
    )

    payload = captured["payload"]
    assert payload["handle_hash"] == hashlib.sha256(handle.encode()).hexdigest()
    assert handle not in str(payload)
    assert payload["refresh_token_ciphertext"] != "refresh-token-secret"
    assert "refresh-token-secret" not in payload["refresh_token_ciphertext"]
    assert payload["user_agent_hash"] == hashlib.sha256(
        b"Browser/1.0"
    ).hexdigest()


def test_load_browser_session_decrypts_only_for_same_user_agent(monkeypatch):
    monkeypatch.setenv("MARKET_FORECASTER_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv(
        "MARKET_FORECASTER_SUPABASE_SERVICE_ROLE_KEY",
        "service-role-super-secret",
    )

    ciphertext = store._fernet().encrypt(b"refresh-old").decode("ascii")
    row = {
        "auth_subject": "11111111-1111-4111-8111-111111111111",
        "refresh_token_ciphertext": ciphertext,
        "user_agent_hash": hashlib.sha256(b"Browser/1.0").hexdigest(),
        "expires_at": "2099-01-01T00:00:00+00:00",
        "revoked_at": None,
    }

    def fake_request_rows(**kwargs):
        if kwargs["method"] == "GET":
            return [row]
        return []

    monkeypatch.setattr(store, "_request_rows", fake_request_rows)

    restored = store.load_browser_session(
        handle="opaque-handle",
        user_agent="Browser/1.0",
    )
    assert restored is not None
    assert restored.refresh_token == "refresh-old"

    rejected = store.load_browser_session(
        handle="opaque-handle",
        user_agent="DifferentBrowser/2.0",
    )
    assert rejected is None


def test_restore_persistent_session_rotates_refresh_token(monkeypatch):
    from market_forecaster.auth import persistent_session as persistent

    stored = store.StoredBrowserSession(
        auth_subject="11111111-1111-4111-8111-111111111111",
        refresh_token="refresh-old",
        expires_at=store.datetime(2099, 1, 1, tzinfo=store.timezone.utc),
    )
    captured = {}

    monkeypatch.setattr(
        persistent,
        "load_browser_session",
        lambda **kwargs: stored,
    )
    monkeypatch.setattr(
        persistent,
        "rotate_browser_refresh_token",
        lambda **kwargs: captured.update(kwargs),
    )

    state = {}
    identity = restore_persistent_browser_session(
        state,
        RefreshingProvider(),
        handle="opaque-handle",
        user_agent="Browser/1.0",
    )

    assert identity is not None
    assert identity.authenticated is True
    assert resolve_identity(state).auth_subject == stored.auth_subject
    assert state[BROWSER_SESSION_HANDLE_KEY] == "opaque-handle"
    assert captured == {
        "handle": "opaque-handle",
        "refresh_token": "refresh-new",
    }
    assert state["requested_plan"] == "pro"


def test_existing_authenticated_session_is_upgraded_to_persistent_storage(monkeypatch):
    from market_forecaster.auth import persistent_session as persistent
    from market_forecaster.auth.session import establish_authenticated_session

    captured = {}

    def fake_create(**kwargs):
        captured["create"] = kwargs
        return "opaque-handle"

    monkeypatch.setattr(persistent, "create_browser_session", fake_create)

    state = {}
    identity = establish_authenticated_session(
        state,
        AuthResult(
            user=AuthUser(
                subject="11111111-1111-4111-8111-111111111111",
                email="user@example.com",
                email_confirmed=True,
            ),
            tokens=AuthTokens(
                access_token="access-current",
                refresh_token="refresh-current",
                expires_in=3600,
            ),
        ),
        provider_name="fake",
    )

    handle = ensure_persistent_browser_session(
        state,
        identity,
        user_agent="Browser/1.0",
    )

    assert handle == "opaque-handle"
    assert state[BROWSER_SESSION_HANDLE_KEY] == "opaque-handle"
    assert captured["create"]["auth_subject"] == identity.auth_subject
    assert captured["create"]["refresh_token"] == "refresh-current"
    assert state["_browser_session_storage_action"] == {
        "action": "set",
        "value": "opaque-handle",
    }
