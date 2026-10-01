from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from market_forecaster.api import security
from market_forecaster.api.middleware import RequestContextMiddleware
from market_forecaster.api.routes import customer_api
from market_forecaster.services.api_keys import APIKeyPrincipal, APIUsageDecision


ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "market_forecaster" / "api" / "main.py"
USER_ID = "11111111-1111-4111-8111-111111111111"


class _Settings:
    api_key = "internal-secret"
    pro_api_monthly_requests = 1000

    @property
    def auth_enabled(self):
        return True


def _customer_principal() -> APIKeyPrincipal:
    return APIKeyPrincipal(
        key_id="key-1",
        user_id=USER_ID,
        key_prefix="mfk_abcdefgh1234",
        plan="pro",
        subscription_status="active",
    )


def _usage() -> APIUsageDecision:
    return APIUsageDecision(
        allowed=True,
        used=7,
        remaining=993,
        monthly_limit=1000,
        period_start="2026-10-01",
        period_end="2026-11-01",
    )


def _customer_usage_client() -> TestClient:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    app.include_router(
        customer_api.router,
        prefix="/api/v1",
        dependencies=[Depends(security.require_customer_api_key)],
    )
    return TestClient(app)


def _internal_only_client() -> TestClient:
    app = FastAPI()

    @app.get(
        "/internal",
        dependencies=[Depends(security.require_internal_api_key)],
    )
    async def internal():
        return {"ok": True}

    return TestClient(app)


def test_customer_usage_endpoint_reports_consumed_account_quota(monkeypatch):
    monkeypatch.setattr(security, "load_settings", lambda: _Settings())
    monkeypatch.setattr(
        security,
        "validate_customer_api_key",
        lambda value: _customer_principal(),
    )
    monkeypatch.setattr(
        security,
        "consume_customer_api_request",
        lambda principal, monthly_limit: _usage(),
    )

    response = _customer_usage_client().get(
        "/api/v1/api/usage",
        headers={"X-API-Key": "mfk_" + "x" * 40},
    )

    assert response.status_code == 200
    assert response.json() == {
        "key_prefix": "mfk_abcdefgh1234",
        "plan": "pro",
        "subscription_status": "active",
        "monthly_limit": 1000,
        "used": 7,
        "remaining": 993,
        "period_start": "2026-10-01",
        "period_end": "2026-11-01",
    }
    assert response.headers["X-Market-Forecaster-API-Remaining"] == "993"


def test_internal_key_cannot_use_customer_usage_endpoint(monkeypatch):
    monkeypatch.setattr(security, "load_settings", lambda: _Settings())

    response = _customer_usage_client().get(
        "/api/v1/api/usage",
        headers={"X-API-Key": "internal-secret"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Pro customer API key required"


def test_customer_key_cannot_call_internal_only_route(monkeypatch):
    monkeypatch.setattr(security, "load_settings", lambda: _Settings())

    response = _internal_only_client().get(
        "/internal",
        headers={"X-API-Key": "mfk_" + "x" * 40},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Internal API authorization required"


def test_internal_key_can_call_internal_only_route(monkeypatch):
    monkeypatch.setattr(security, "load_settings", lambda: _Settings())

    response = _internal_only_client().get(
        "/internal",
        headers={"X-API-Key": "internal-secret"},
    )

    assert response.status_code == 200


def test_operational_routes_are_internal_only_and_hidden_from_public_docs():
    source = MAIN.read_text(encoding="utf-8")

    for router_name in (
        "options_promotion_routes.router",
        "audit_routes.router",
        "deployment_policy_routes.router",
        "operations_routes.router",
        "data_provider_routes.router",
    ):
        start = source.index(f"app.include_router(\n    {router_name}")
        block = source[start : start + 350]
        assert "dependencies=internal_only" in block
        assert "include_in_schema=False" in block

    assert "customer_api_routes.router" in source
    assert "dependencies=customer_only" in source
