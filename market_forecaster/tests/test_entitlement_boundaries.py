from __future__ import annotations

from market_forecaster.core.entitlements import (
    can_save_forecast_history,
    can_save_portfolio,
    can_save_watchlist,
    can_use_api,
    can_use_ticker,
    can_view_research_lab,
    entitlements_for,
)
from market_forecaster.core.session_identity import AppIdentity


def _identity(plan: str, *, authenticated: bool = True) -> AppIdentity:
    return AppIdentity(
        user_id="user",
        session_id="session",
        authenticated=authenticated,
        plan=plan,
        subscription_status="active" if plan != "demo" else "none",
        is_admin=False,
        auth_provider="supabase" if authenticated else None,
        auth_subject="11111111-1111-4111-8111-111111111111"
        if authenticated
        else None,
    )


def test_signed_in_demo_account_does_not_gain_paid_ticker_access():
    identity = _identity("demo")

    assert can_use_ticker(identity, "AAPL") is True
    assert can_use_ticker(identity, "SPY") is True
    assert can_use_ticker(identity, "NVDA") is False
    assert can_use_ticker(identity, "ETH-USD") is False


def test_signed_in_demo_account_has_no_persistent_or_expensive_features():
    identity = _identity("demo")
    rules = entitlements_for(identity)

    assert rules.expensive_refreshes_per_day == 0
    assert can_save_watchlist(identity) is False
    assert can_save_portfolio(identity) is False
    assert can_save_forecast_history(identity) is False
    assert can_view_research_lab(identity) is False
    assert can_use_api(identity) is False


def test_standard_and_pro_keep_expected_paid_boundaries():
    standard = _identity("standard")
    pro = _identity("pro")

    assert can_use_ticker(standard, "NVDA") is True
    assert entitlements_for(standard).expensive_refreshes_per_day > 0
    assert can_save_watchlist(standard) is True
    assert can_view_research_lab(standard) is False
    assert can_use_api(standard) is False

    assert can_use_ticker(pro, "NVDA") is True
    assert can_view_research_lab(pro) is True
    assert can_use_api(pro) is True
