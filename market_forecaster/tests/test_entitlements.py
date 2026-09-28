from market_forecaster.core.entitlements import (
    can_export_forecast,
    entitlements_for,
)
from market_forecaster.core.session_identity import AppIdentity


def _identity(plan: str, *, is_admin: bool = False) -> AppIdentity:
    return AppIdentity(
        user_id="user-1",
        session_id="session-1",
        authenticated=plan != "demo",
        plan=plan,
        subscription_status="active" if plan != "demo" else "none",
        is_admin=is_admin,
        auth_provider="supabase" if plan != "demo" else None,
        auth_subject="11111111-1111-4111-8111-111111111111"
        if plan != "demo"
        else None,
    )


def test_forecast_export_is_standard_and_pro_entitlement():
    assert can_export_forecast(_identity("demo")) is False
    assert can_export_forecast(_identity("standard")) is True
    assert can_export_forecast(_identity("pro")) is True


def test_admin_retains_forecast_export_entitlement():
    rules = entitlements_for(_identity("demo", is_admin=True))

    assert rules.forecast_export is True
