from pathlib import Path

from market_forecaster.api.settings import load_settings
from market_forecaster.core.session_identity import AppIdentity
from market_forecaster.services import api_keys
from market_forecaster.services.api_keys import (
    APIKeyPrincipal,
    consume_customer_api_request,
    get_user_api_usage,
)


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260928230000_api_usage_monthly.sql"
)
USER_ID = "11111111-1111-4111-8111-111111111111"


def _principal() -> APIKeyPrincipal:
    return APIKeyPrincipal(
        key_id="22222222-2222-4222-8222-222222222222",
        user_id=USER_ID,
        key_prefix="mfk_exampleprefix",
        plan="pro",
        subscription_status="active",
    )


def _identity() -> AppIdentity:
    return AppIdentity(
        user_id="internal",
        session_id="session",
        authenticated=True,
        plan="pro",
        subscription_status="active",
        auth_provider="supabase",
        auth_subject=USER_ID,
    )


def test_usage_migration_is_account_wide_and_service_role_only():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "primary key (user_id, period_start)" in sql
    assert "api_key_id" not in sql
    assert "enable row level security" in sql
    assert "to anon, authenticated" in sql
    assert "using (false)" in sql
    assert "grant execute on function public.consume_market_forecaster_api_request" in sql
    assert "to service_role" in sql


def test_consume_customer_api_request_returns_quota_decision(monkeypatch):
    monkeypatch.setattr(
        api_keys,
        "_rpc_rows",
        lambda function_name, payload, timeout_seconds=5.0: [
            {
                "allowed": True,
                "used": 25,
                "remaining": 975,
                "period_start": "2026-09-01",
                "period_end": "2026-10-01",
            }
        ],
    )

    decision = consume_customer_api_request(_principal(), monthly_limit=1000)

    assert decision.allowed is True
    assert decision.used == 25
    assert decision.remaining == 975
    assert decision.monthly_limit == 1000
    assert decision.period_end == "2026-10-01"


def test_user_usage_summary_is_account_wide(monkeypatch):
    monkeypatch.setattr(
        api_keys,
        "verified_owner_id",
        lambda identity: USER_ID,
    )
    monkeypatch.setattr(
        api_keys,
        "_request_rows",
        lambda table, **kwargs: [
            {
                "request_count": 125,
                "period_start": "2026-09-01",
                "updated_at": "2026-09-28T20:00:00Z",
            }
        ],
    )

    summary = get_user_api_usage(_identity(), monthly_limit=1000)

    assert summary["used"] == 125
    assert summary["remaining"] == 875
    assert summary["monthly_limit"] == 1000


def test_api_settings_default_to_sellable_pro_quota(monkeypatch):
    monkeypatch.setenv("MARKET_FORECASTER_ENV", "test")
    monkeypatch.delenv("MARKET_FORECASTER_PRO_API_MONTHLY_REQUESTS", raising=False)

    settings = load_settings()

    assert settings.pro_api_monthly_requests == 1000


def test_api_settings_allow_quota_to_change_without_code(monkeypatch):
    monkeypatch.setenv("MARKET_FORECASTER_ENV", "test")
    monkeypatch.setenv("MARKET_FORECASTER_PRO_API_MONTHLY_REQUESTS", "2500")

    settings = load_settings()

    assert settings.pro_api_monthly_requests == 2500



def test_production_api_settings_reject_non_positive_monthly_quota(monkeypatch):
    monkeypatch.setenv("MARKET_FORECASTER_ENV", "production")
    monkeypatch.setenv("MARKET_FORECASTER_API_KEY", "internal-secret")
    monkeypatch.setenv(
        "MARKET_FORECASTER_ALLOWED_ORIGINS",
        "https://marketforecaster.oneeightaisystems.com",
    )
    monkeypatch.setenv("MARKET_FORECASTER_PRO_API_MONTHLY_REQUESTS", "0")

    try:
        load_settings()
    except RuntimeError as exc:
        assert "MONTHLY_REQUESTS" in str(exc)
    else:
        raise AssertionError("Expected production settings to reject zero API quota")
