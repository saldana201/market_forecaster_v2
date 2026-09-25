from __future__ import annotations

from market_forecaster.ui.market_cards import (
    forecast_for_horizon,
    group_watchlist_symbols,
)


def test_forecast_for_horizon_returns_exact_requested_row():
    forecasts = [
        {"horizon_days": 1, "projected_price": 101},
        {"horizon_days": 5, "projected_price": 105},
        {"horizon_days": 10, "projected_price": 110},
        {"horizon_days": 20, "projected_price": 120},
    ]

    assert forecast_for_horizon(forecasts, 1)["projected_price"] == 101
    assert forecast_for_horizon(forecasts, 5)["projected_price"] == 105
    assert forecast_for_horizon(forecasts, 10)["projected_price"] == 110
    assert forecast_for_horizon(forecasts, 20)["projected_price"] == 120
    assert forecast_for_horizon(forecasts, 7) is None


def test_watchlist_grouping_uses_demo_sector_metadata_and_stable_order():
    status_map = {
        "AAPL": {"display_name": "Apple", "category": "Technology"},
        "JPM": {"display_name": "JPMorgan Chase", "category": "Financials"},
        "XOM": {"display_name": "Exxon Mobil", "category": "Energy"},
    }

    groups = group_watchlist_symbols(["XOM", "AAPL", "JPM"], status_map)

    assert list(groups) == ["Technology", "Financials", "Energy"]
    assert [row.ticker for row in groups["Technology"]] == ["AAPL"]
    assert [row.ticker for row in groups["Financials"]] == ["JPM"]
    assert [row.ticker for row in groups["Energy"]] == ["XOM"]


def test_unknown_custom_tickers_fall_into_other_sector():
    groups = group_watchlist_symbols(
        ["NVDA"],
        {"NVDA": {"display_name": "NVDA", "available": False}},
    )

    assert list(groups) == ["Other"]
    assert groups["Other"][0].ticker == "NVDA"
