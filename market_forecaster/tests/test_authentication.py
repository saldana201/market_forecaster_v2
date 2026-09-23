from __future__ import annotations

from io import BytesIO
from urllib import error

from fastapi import FastAPI
from fastapi.testclient import TestClient

from market_forecaster.api.routes import account as account_routes
from market_forecaster.auth.provider import AuthResult, AuthTokens, AuthUser, InvalidToken, RateLimited
from market_forecaster.auth.supabase import SupabaseAuthProvider
from market_forecaster.auth.session import (
    AUTH_SESSION_KEY,
    clear_authenticated_session,
    establish_authenticated_session,
    stable_internal_user_id,
    sync_authenticated_identity,
)
from market_forecaster.core.session_identity import resolve_identity


class FakeAuthProvider:
    name = "fake"

    def register(self, email: str, password: str, display_name: str | None = None) -> AuthResult:
        return AuthResult(
            user=AuthUser("subject-register", email, display_name, True),
            tokens=AuthTokens("good-register"),
        )

    def login(self, email: str, password: str) -> AuthResult:
        return AuthResult(
            user=AuthUser("subject-login", email, "Test User", True),
            tokens=AuthTokens("good-a"),
        )

    def logout(self, access_token: str) -> None:
        return None

    def verify_token(self, access_token: str) -> AuthUser:
        if access_token == "good-a":
            return AuthUser("subject-a", "a@example.com", "A", True)
        if access_token == "good-b":
            return AuthUser("subject-b", "b@example.com", "B", True)
        raise InvalidToken("expired or invalid")


def test_internal_user_id_is_stable_and_provider_subject_scoped():
    first = stable_internal_user_id("fake", "subject-a")
    second = stable_internal_user_id("fake", "subject-a")
    other_user = stable_internal_user_id("fake", "subject-b")
    other_provider = stable_internal_user_id("other", "subject-a")

    assert first == second
    assert first != other_user
    assert first != other_provider


def test_authenticated_session_uses_verified_subject_not_email():
    state = {}
    result = AuthResult(
        user=AuthUser(
            subject="provider-subject-123",
            email="same@example.com",
            display_name="Tester",
            email_confirmed=True,
        ),
        tokens=AuthTokens(access_token="token-123"),
    )

    identity = establish_authenticated_session(state, result, provider_name="fake")

    assert identity.authenticated is True
    assert identity.user_id == stable_internal_user_id("fake", "provider-subject-123")
    assert identity.auth_subject == "provider-subject-123"
    assert state[AUTH_SESSION_KEY]["access_token"] == "token-123"


def test_second_verified_subject_receives_different_uuid():
    state_a = {}
    state_b = {}
    provider = FakeAuthProvider()

    establish_authenticated_session(
        state_a,
        AuthResult(AuthUser("subject-a"), AuthTokens("good-a")),
        provider_name=provider.name,
    )
    establish_authenticated_session(
        state_b,
        AuthResult(AuthUser("subject-b"), AuthTokens("good-b")),
        provider_name=provider.name,
    )

    assert resolve_identity(state_a).user_id != resolve_identity(state_b).user_id


def test_expired_token_is_rejected_and_session_returns_to_demo():
    state = {}
    establish_authenticated_session(
        state,
        AuthResult(AuthUser("subject-a"), AuthTokens("expired")),
        provider_name="fake",
    )

    provider = FakeAuthProvider()
    try:
        sync_authenticated_identity(state, provider)
        assert False, "Expected InvalidToken"
    except InvalidToken:
        pass

    identity = resolve_identity(state)
    assert identity.authenticated is False
    assert identity.user_id is None
    assert identity.plan == "demo"


def test_logout_clears_authenticated_identity_but_preserves_demo_session():
    state = {}
    establish_authenticated_session(
        state,
        AuthResult(AuthUser("subject-a"), AuthTokens("good-a")),
        provider_name="fake",
    )
    session_id = resolve_identity(state).session_id

    identity = clear_authenticated_session(state)

    assert identity.authenticated is False
    assert identity.user_id is None
    assert identity.session_id == session_id
    assert AUTH_SESSION_KEY not in state


def test_account_api_derives_identity_from_bearer_token(monkeypatch):
    provider = FakeAuthProvider()
    monkeypatch.setattr(
        "market_forecaster.api.user_auth.get_auth_provider",
        lambda: provider,
    )

    app = FastAPI()
    app.include_router(account_routes.router, prefix="/api/v1")
    client = TestClient(app)

    response = client.get(
        "/api/v1/account/me?user_id=spoofed-user",
        headers={"Authorization": "Bearer good-a"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == stable_internal_user_id("fake", "subject-a")
    assert payload["user_id"] != "spoofed-user"
    assert payload["authenticated"] is True


def test_account_api_rejects_invalid_or_expired_token(monkeypatch):
    provider = FakeAuthProvider()
    monkeypatch.setattr(
        "market_forecaster.api.user_auth.get_auth_provider",
        lambda: provider,
    )

    app = FastAPI()
    app.include_router(account_routes.router, prefix="/api/v1")
    client = TestClient(app)

    response = client.get(
        "/api/v1/account/me",
        headers={"Authorization": "Bearer expired"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired bearer token"


def test_supabase_signup_rate_limit_exposes_retry_seconds(monkeypatch):
    provider = SupabaseAuthProvider(
        "https://example.supabase.co",
        "sb_publishable_test",
    )

    body = b'{"message":"For security purposes, you can only request this after 37 seconds."}'
    http_error = error.HTTPError(
        url="https://example.supabase.co/auth/v1/signup",
        code=429,
        msg="Too Many Requests",
        hdrs={},
        fp=BytesIO(body),
    )

    def raise_rate_limit(*args, **kwargs):
        raise http_error

    monkeypatch.setattr(
        "market_forecaster.auth.supabase.request.urlopen",
        raise_rate_limit,
    )

    try:
        provider.register("test@example.com", "password123", "Test User")
        assert False, "Expected RateLimited"
    except RateLimited as exc:
        assert exc.retry_after_seconds == 37
        assert "37 seconds" in str(exc)


def test_supabase_signup_accepts_top_level_user_response(monkeypatch):
    provider = SupabaseAuthProvider(
        "https://example.supabase.co",
        "sb_publishable_test",
    )

    payload = {
        "id": "82a2b547-f82b-4a6c-b75a-7b04b94dc5e0",
        "email": "jrsaldana32@gmail.com",
        "user_metadata": {"display_name": "Saldana"},
        "email_confirmed_at": None,
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            import json
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(
        "market_forecaster.auth.supabase.request.urlopen",
        lambda *args, **kwargs: FakeResponse(),
    )

    result = provider.register(
        "jrsaldana32@gmail.com",
        "password123",
        "Saldana",
    )

    assert result.user.subject == payload["id"]
    assert result.user.email == "jrsaldana32@gmail.com"
    assert result.user.display_name == "Saldana"
    assert result.tokens is None
    assert result.requires_email_confirmation is True


def test_supabase_signup_still_accepts_nested_user_response(monkeypatch):
    provider = SupabaseAuthProvider(
        "https://example.supabase.co",
        "sb_publishable_test",
    )

    payload = {
        "user": {
            "id": "11111111-1111-4111-8111-111111111111",
            "email": "nested@example.com",
            "user_metadata": {"display_name": "Nested"},
            "email_confirmed_at": None,
        }
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            import json
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(
        "market_forecaster.auth.supabase.request.urlopen",
        lambda *args, **kwargs: FakeResponse(),
    )

    result = provider.register("nested@example.com", "password123", "Nested")

    assert result.user.subject == payload["user"]["id"]
    assert result.requires_email_confirmation is True
