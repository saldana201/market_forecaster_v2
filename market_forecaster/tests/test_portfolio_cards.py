from __future__ import annotations

import math

from market_forecaster.ui.portfolio_cards import build_portfolio_snapshot


def _status(price: float, category: str = "Technology") -> dict:
    return {
        "current_price": price,
        "category": category,
        "display_name": "Example",
        "forecasts": [
            {
                "horizon_days": 10,
                "projected_price": price * 1.05,
                "expected_return_pct": 5.0,
                "probability_up_pct": 65.0,
            }
        ],
    }


def test_portfolio_snapshot_calculates_value_pnl_return_and_cash():
    positions = [
        {"ticker": "AAPL", "quantity": 2, "avg_cost": 100},
        {"ticker": "MSFT", "quantity": 1, "avg_cost": 200},
    ]
    statuses = {
        "AAPL": _status(120),
        "MSFT": _status(180),
    }

    snap = build_portfolio_snapshot(
        positions,
        1000,
        statuses,
        cost_key="avg_cost",
    )

    assert snap["holdings_value"] == 420
    assert snap["portfolio_value"] == 1420
    assert snap["invested_capital"] == 400
    assert snap["unrealized"] == 20
    assert math.isclose(snap["return_pct"], 5.0)
    assert math.isclose(snap["cash_pct"], (1000 / 1420) * 100)


def test_portfolio_snapshot_allocates_by_market_exposure():
    positions = [
        {"ticker": "AAPL", "quantity": 2, "avg_cost": 100},
        {"ticker": "XOM", "quantity": 4, "avg_cost": 50},
    ]
    statuses = {
        "AAPL": _status(100, "Technology"),
        "XOM": _status(50, "Energy"),
    }

    snap = build_portfolio_snapshot(
        positions,
        0,
        statuses,
        cost_key="avg_cost",
    )

    by_sector = {row["sector"]: row for row in snap["sector_allocations"]}
    assert math.isclose(by_sector["Technology"]["allocation_pct"], 50.0)
    assert math.isclose(by_sector["Energy"]["allocation_pct"], 50.0)


def test_portfolio_snapshot_preserves_missing_prices_without_crashing():
    positions = [{"ticker": "CUSTOM", "quantity": 3, "avg_cost": 20}]
    statuses = {
        "CUSTOM": {
            "current_price": None,
            "category": "Other",
            "display_name": "CUSTOM",
            "forecasts": [],
        }
    }

    snap = build_portfolio_snapshot(
        positions,
        500,
        statuses,
        cost_key="avg_cost",
    )

    assert snap["portfolio_value"] == 500
    assert snap["invested_capital"] == 60
    assert snap["positions"][0]["market_value"] is None
    assert snap["positions"][0]["unrealized"] is None
