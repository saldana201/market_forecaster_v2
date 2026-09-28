from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from market_forecaster.api import security
from market_forecaster.api.middleware import RateLimitMiddleware
from market_forecaster.core.session_identity import AppIdentity
from market_forecaster.services import api_keys
from market_forecaster.services.api_keys import (
    APIKeyPrincipal,
    APIKeyStoreError,
    InvalidCustomerAPIKey,
    create_user_api_key,
    validate_customer_api_key,
)


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase" / "migrations" / "20260928100000_user_api_keys.sql"
USER_ID = "11111111-1111-4111-8111-111111111111"


def _identity(plan: str) -> AppIdentity:
    return AppIdentity(
        user_id="internal",
        session_id="session",
        authenticated=True,
        plan=plan,
        subscription_status="active",
        auth_provider="supabase",
        auth_subject=USER_ID,
    )


def test_customer_api_key_creation_stores_only_hash(monkeypatch):
    calls = []

    def fake_request(table, **kwargs):
        calls.append((table, kwargs))
        if kwargs.get("method", "GET") == "GET":
            return []
        payload = kwargs["payload"]
        return [
            {
                "id": "key-1",
                "name": payload["name"],
                "key_prefix": payload["key_prefix"],
                "created_at": "2026-09-28T12:00:00Z",
            }
        ]

    monkeypatch.setattr(api_keys, "_request_rows", fake_request)

    created = create_user_api_key(_identity("pro"), name="Automation")

    assert created["api_key"].startswith("mfk_")
    insert_payload = calls[-1][1]["payload"]
    assert "api_key" not in insert_payload
    assert "plaintext" not in insert_payload
    assert len(insert_payload["key_hash"]) == 64
    assert insert_payload["key_prefix"] == created["key_prefix"]
    assert created["api_key"] not in str(insert_payload)


def test_customer_api_key_creation_requires_pro(monkeypatch):
    monkeypatch.setattr(
        api_keys,
        "_request_rows",
        lambda *args, **kwargs: pytest.fail("storage should not be called"),
    )

    with pytest.raises(APIKeyStoreError, match="Pro"):
        create_user_api_key(_identity("standard"), name="Should fail")


def test_customer_api_key_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(
        api_keys,
        "list_user_api_keys",
        lambda identity: [{"id": str(i)} for i in range(5)],
    )

    with pytest.raises(APIKeyStoreError, match="At most 5"):
        create_user_api_key(_identity("pro"), name="Sixth")


def test_customer_api_key_validation_rechecks_pro_subscription(monkeypatch):
    monkeypatch.setattr(api_keys, "SUBSCRIPTIONS_ENABLED", True)
    calls = []

    def fake_request(table, **kwargs):
        calls.append((table, kwargs))
        if table == "user_api_keys" and kwargs.get("method", "GET") == "GET":
            return [
                {
                    "id": "key-1",
                    "user_id": USER_ID,
                    "key_prefix": "mfk_abcdefgh1234",
                    "revoked_at": None,
                }
            ]
        if table == "subscriptions":
            return [{"plan": "pro", "status": "active"}]
        return []

    monkeypatch.setattr(api_keys, "_request_rows", fake_request)

    principal = validate_customer_api_key("mfk_" + "x" * 40)

    assert principal.user_id == USER_ID
    assert principal.plan == "pro"
    assert principal.subscription_status == "active"
    assert any(
        table == "user_api_keys" and kwargs.get("method") == "PATCH"
        for table, kwargs in calls
    )


def test_customer_api_key_validation_rejects_non_pro_subscription(monkeypatch):
    monkeypatch.setattr(api_keys, "SUBSCRIPTIONS_ENABLED", True)

    def fake_request(table, **kwargs):
        if table == "user_api_keys":
            return [
                {
                    "id": "key-1",
                    "user_id": USER_ID,
                    "key_prefix": "mfk_abcdefgh1234",
                }
            ]
        if table == "subscriptions":
            return [{"plan": "standard", "status": "active"}]
        return []

    monkeypatch.setattr(api_keys, "_request_rows", fake_request)

    with pytest.raises(InvalidCustomerAPIKey, match="Pro"):
        validate_customer_api_key("mfk_" + "x" * 40)


def test_customer_api_key_validation_is_disabled_with_subscriptions(monkeypatch):
    monkeypatch.setattr(api_keys, "SUBSCRIPTIONS_ENABLED", False)

    with pytest.raises(InvalidCustomerAPIKey, match="not enabled"):
        validate_customer_api_key("mfk_" + "x" * 40)


def test_customer_api_key_migration_is_service_role_only():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "key_hash text not null unique" in sql
    assert "api_key text" not in sql.lower()
    assert "plaintext text" not in sql.lower()
    assert "enable row level security" in sql.lower()
    assert "revoke all on table public.user_api_keys from public, anon, authenticated" in sql
    assert "grant select, insert, update, delete on table public.user_api_keys to service_role" in sql


class _Settings:
    def __init__(self, api_key="internal-secret"):
        self.api_key = api_key

    @property
    def auth_enabled(self):
        return bool(self.api_key)


def _security_client() -> TestClient:
    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(security.require_api_key)])
    async def protected():
        return {"ok": True}

    return TestClient(app)


def test_internal_api_key_still_works(monkeypatch):
    monkeypatch.setattr(security, "load_settings", lambda: _Settings())

    response = _security_client().get(
        "/protected",
        headers={"X-API-Key": "internal-secret"},
    )

    assert response.status_code == 200


def test_pro_customer_api_key_is_accepted(monkeypatch):
    monkeypatch.setattr(security, "load_settings", lambda: _Settings())
    monkeypatch.setattr(
        security,
        "validate_customer_api_key",
        lambda value: APIKeyPrincipal(
            key_id="key-1",
            user_id=USER_ID,
            key_prefix="mfk_abcdefgh1234",
            plan="pro",
            subscription_status="active",
        ),
    )

    response = _security_client().get(
        "/protected",
        headers={"X-API-Key": "mfk_" + "x" * 40},
    )

    assert response.status_code == 200


def test_invalid_customer_api_key_is_401(monkeypatch):
    monkeypatch.setattr(security, "load_settings", lambda: _Settings())

    def fail(_value):
        raise InvalidCustomerAPIKey("nope")

    monkeypatch.setattr(security, "validate_customer_api_key", fail)

    response = _security_client().get(
        "/protected",
        headers={"X-API-Key": "mfk_" + "x" * 40},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or inactive API key"


def test_customer_api_key_backend_outage_is_503(monkeypatch):
    monkeypatch.setattr(security, "load_settings", lambda: _Settings())

    def fail(_value):
        raise APIKeyStoreError("offline")

    monkeypatch.setattr(security, "validate_customer_api_key", fail)

    response = _security_client().get(
        "/protected",
        headers={"X-API-Key": "mfk_" + "x" * 40},
    )

    assert response.status_code == 503



def test_customer_api_key_rate_limit_follows_key_across_source_ips():
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        requests=2,
        window_seconds=60,
        shared_limiter=None,
    )

    @app.get("/api/v1/ping")
    async def ping():
        return {"ok": True}

    client = TestClient(app)
    customer_key = "mfk_" + "r" * 40

    first = client.get(
        "/api/v1/ping",
        headers={"X-API-Key": customer_key, "X-Forwarded-For": "10.0.0.1"},
    )
    second = client.get(
        "/api/v1/ping",
        headers={"X-API-Key": customer_key, "X-Forwarded-For": "10.0.0.2"},
    )
    third = client.get(
        "/api/v1/ping",
        headers={"X-API-Key": customer_key, "X-Forwarded-For": "10.0.0.3"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
