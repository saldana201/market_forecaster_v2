"""Centralized product entitlements for Market Forecaster 4.1.0."""
from __future__ import annotations

from dataclasses import dataclass

from market_forecaster.core.demo_universe import is_demo_ticker
from market_forecaster.core.session_identity import AppIdentity


@dataclass(frozen=True)
class PlanEntitlements:
    custom_tickers: bool
    watchlist_limit: int
    portfolio_limit: int
    positions_per_portfolio: int
    expensive_refreshes_per_day: int
    persistent_storage: bool
    research_lab: bool
    api_access: bool


ENTITLEMENTS: dict[str, PlanEntitlements] = {
    "demo": PlanEntitlements(
        custom_tickers=False,
        watchlist_limit=6,
        portfolio_limit=1,
        positions_per_portfolio=10,
        expensive_refreshes_per_day=0,
        persistent_storage=False,
        research_lab=False,
        api_access=False,
    ),
    "standard": PlanEntitlements(
        custom_tickers=True,
        watchlist_limit=50,
        portfolio_limit=3,
        positions_per_portfolio=100,
        expensive_refreshes_per_day=50,
        persistent_storage=True,
        research_lab=False,
        api_access=False,
    ),
    "pro": PlanEntitlements(
        custom_tickers=True,
        watchlist_limit=250,
        portfolio_limit=10,
        positions_per_portfolio=500,
        expensive_refreshes_per_day=200,
        persistent_storage=True,
        research_lab=True,
        api_access=True,
    ),
}


def entitlements_for(identity: AppIdentity) -> PlanEntitlements:
    if identity.is_admin:
        return PlanEntitlements(True, 10000, 10000, 10000, 10000, True, True, True)
    return ENTITLEMENTS.get(identity.plan, ENTITLEMENTS["demo"])


def can_use_ticker(identity: AppIdentity, ticker: str) -> bool:
    rules = entitlements_for(identity)
    return bool(rules.custom_tickers or is_demo_ticker(ticker))


def can_save_watchlist(identity: AppIdentity) -> bool:
    return entitlements_for(identity).persistent_storage


def can_save_portfolio(identity: AppIdentity) -> bool:
    return entitlements_for(identity).persistent_storage


def can_save_forecast_history(identity: AppIdentity) -> bool:
    return entitlements_for(identity).persistent_storage


def can_view_research_lab(identity: AppIdentity) -> bool:
    return entitlements_for(identity).research_lab


def can_run_cross_ticker_validation(identity: AppIdentity) -> bool:
    return entitlements_for(identity).research_lab


def can_use_api(identity: AppIdentity) -> bool:
    return entitlements_for(identity).api_access


def check_watchlist_limit(identity: AppIdentity, item_count: int) -> bool:
    return int(item_count) <= entitlements_for(identity).watchlist_limit


def check_position_limit(identity: AppIdentity, position_count: int) -> bool:
    return int(position_count) <= entitlements_for(identity).positions_per_portfolio


def check_forecast_quota(identity: AppIdentity, refreshes_used: int) -> bool:
    limit = entitlements_for(identity).expensive_refreshes_per_day
    return int(refreshes_used) < limit
