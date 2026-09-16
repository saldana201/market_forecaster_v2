from __future__ import annotations

import pandas as pd
import pytest

from market_forecaster.core import portfolio


def _market(price=100.0):
    df = pd.DataFrame({
        "Date": pd.bdate_range("2026-01-01", periods=30),
        "Close": [price] * 30,
    })
    df.attrs["provider"] = "test"
    return df


def _base_ranking():
    return {
        "generated_at_utc": "2026-09-15T00:00:00+00:00",
        "correlation_matrix": {},
        "correlation_return_rows": {},
        "ranked": [
            {
                "rank": 1,
                "ticker": "AAA",
                "horizon": 20,
                "recommendation": "LONG_SETUP",
                "actionable": True,
                "direction": "BULLISH",
                "direction_bucket": "LONG",
                "evidence_status": "CALIBRATED",
                "ranking_score": 80.0,
                "research_risk_budget_pct": 20.0,
                "reference_entry": 100.0,
                "decision_target": 115.0,
                "invalidation": 95.0,
            },
            {
                "rank": 2,
                "ticker": "BBB",
                "horizon": 20,
                "recommendation": "LONG_SETUP",
                "actionable": True,
                "direction": "BULLISH",
                "direction_bucket": "LONG",
                "evidence_status": "CALIBRATED",
                "ranking_score": 70.0,
                "research_risk_budget_pct": 20.0,
                "reference_entry": 50.0,
                "decision_target": 60.0,
                "invalidation": 45.0,
            },
        ],
    }


def _patch_prices(monkeypatch, prices=None):
    prices = prices or {"AAA": 100.0, "BBB": 50.0, "CCC": 25.0}
    monkeypatch.setattr(
        portfolio,
        "fetch_stock_data",
        lambda ticker, period="1mo", interval="1d": _market(prices.get(ticker, 100.0)),
    )
    monkeypatch.setattr(
        portfolio,
        "load_decision_snapshot",
        lambda ticker: {},
    )


def test_duplicate_position_is_rejected():
    with pytest.raises(ValueError):
        portfolio.normalize_positions([
            {"ticker": "AAA", "quantity": 1, "cost_basis": 100},
            {"ticker": "AAA", "quantity": 2, "cost_basis": 101},
        ])


def test_portfolio_state_roundtrip(tmp_path):
    saved = portfolio.save_portfolio_state(
        1000,
        [{"ticker": "AAA", "quantity": 2, "cost_basis": 90}],
        base_dir=tmp_path,
    )
    loaded = portfolio.load_portfolio_state(base_dir=tmp_path)
    assert saved["cash"] == loaded["cash"] == 1000
    assert loaded["positions"][0]["ticker"] == "AAA"


def test_long_position_unrealized_profit(monkeypatch):
    _patch_prices(monkeypatch, {"AAA": 110.0})
    state = {"cash": 1000, "positions": [
        {"ticker": "AAA", "quantity": 10, "cost_basis": 100}
    ]}
    valued = portfolio.value_portfolio(state, base_ranking=_base_ranking())
    row = valued["positions"][0]
    assert row["unrealized_pl"] == 100.0
    assert row["side"] == "LONG"


def test_existing_concentration_reduces_score_and_budget(monkeypatch):
    _patch_prices(monkeypatch, {"AAA": 100.0, "BBB": 50.0})
    monkeypatch.setattr(
        portfolio,
        "build_return_correlation",
        lambda tickers, period="6mo": ({}, {}),
    )
    state = {
        "cash": 1000,
        "positions": [{"ticker": "AAA", "quantity": 3, "cost_basis": 100}],
    }
    result = portfolio.build_portfolio_aware_ranking(
        _base_ranking(),
        state,
        max_position_pct=20,
        include_portfolio_correlation=False,
    )
    aaa = next(x for x in result["ranked"] if x["ticker"] == "AAA")
    assert aaa["current_position_weight_pct"] > 20
    assert aaa["portfolio_ranking_score"] < aaa["ranking_score"]
    assert aaa["portfolio_research_budget_pct"] == 0


def test_opposite_position_creates_conflict(monkeypatch):
    _patch_prices(monkeypatch)
    state = {
        "cash": 1000,
        "positions": [{"ticker": "AAA", "quantity": -1, "cost_basis": 100}],
    }
    result = portfolio.build_portfolio_aware_ranking(
        _base_ranking(),
        state,
        include_portfolio_correlation=False,
    )
    aaa = next(x for x in result["ranked"] if x["ticker"] == "AAA")
    assert aaa["position_conflict"]
    assert aaa["portfolio_action"] == "POSITION_CONFLICT"
    assert aaa["portfolio_research_budget_pct"] == 0


def test_breached_invalidation_creates_exit_review(monkeypatch):
    _patch_prices(monkeypatch, {"AAA": 94.0, "BBB": 50.0})
    state = {
        "cash": 1000,
        "positions": [{"ticker": "AAA", "quantity": 1, "cost_basis": 100}],
    }
    result = portfolio.build_portfolio_aware_ranking(
        _base_ranking(),
        state,
        include_portfolio_correlation=False,
    )
    aaa = next(x for x in result["ranked"] if x["ticker"] == "AAA")
    assert aaa["invalidation_breached"]
    assert aaa["portfolio_action"] == "EXIT_REVIEW"
    assert aaa["portfolio_research_budget_pct"] == 0


def test_correlated_existing_exposure_consumes_cluster_headroom(monkeypatch):
    _patch_prices(monkeypatch)
    matrix = {
        "AAA": {"AAA": 1.0, "CCC": 0.90},
        "BBB": {"BBB": 1.0, "CCC": 0.10},
        "CCC": {"AAA": 0.90, "BBB": 0.10, "CCC": 1.0},
    }
    monkeypatch.setattr(
        portfolio,
        "build_return_correlation",
        lambda tickers, period="6mo": (matrix, {t: 100 for t in tickers}),
    )
    state = {
        "cash": 500,
        "positions": [{"ticker": "CCC", "quantity": 20, "cost_basis": 25}],
    }
    result = portfolio.build_portfolio_aware_ranking(
        _base_ranking(),
        state,
        max_correlated_cluster_pct=40,
        include_portfolio_correlation=True,
    )
    aaa = next(x for x in result["ranked"] if x["ticker"] == "AAA")
    bbb = next(x for x in result["ranked"] if x["ticker"] == "BBB")
    assert aaa["correlated_existing_exposure_pct"] > bbb["correlated_existing_exposure_pct"]
    assert aaa["portfolio_correlation_multiplier"] <= bbb["portfolio_correlation_multiplier"]


def test_new_entry_budget_never_exceeds_3_4_budget(monkeypatch):
    _patch_prices(monkeypatch)
    state = {"cash": 1000, "positions": []}
    result = portfolio.build_portfolio_aware_ranking(
        _base_ranking(),
        state,
        include_portfolio_correlation=False,
    )
    for row in result["ranked"]:
        assert row["portfolio_research_budget_pct"] <= row["research_risk_budget_pct"]
