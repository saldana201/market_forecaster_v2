from __future__ import annotations

import json

import pytest

from market_forecaster.core.demo_universe import demo_groups, demo_tickers, is_demo_ticker
from market_forecaster.core.entitlements import (
    can_use_ticker,
    can_view_research_lab,
    check_position_limit,
    check_watchlist_limit,
)
from market_forecaster.core.session_identity import ensure_demo_session, resolve_identity
from market_forecaster.services.forecast_access import (
    CachedForecastUnavailable,
    TickerNotEntitled,
    load_demo_forecast,
)


def test_demo_universe_has_expected_14_symbols():
    tickers = demo_tickers()
    assert len(tickers) == 14
    assert {"AAPL", "MSFT", "JPM", "BAC", "LLY", "JNJ", "XOM", "CVX", "WMT", "COST", "CAT", "GE", "SPY", "QQQ"} == set(tickers)


def test_demo_groups_are_registry_driven():
    groups = demo_groups()
    assert "Technology" in groups
    assert [row.ticker for row in groups["Technology"]] == ["AAPL", "MSFT"]


def test_two_demo_sessions_do_not_share_state():
    browser_a = {}
    browser_b = {}
    session_a = ensure_demo_session(browser_a)
    session_b = ensure_demo_session(browser_b)

    session_a["watchlist"].append("AAPL")
    session_a["portfolio"]["positions"].append({"ticker": "AAPL", "quantity": 10, "cost_basis": 200.0})

    assert session_a["session_id"] != session_b["session_id"]
    assert session_b["watchlist"] == []
    assert session_b["portfolio"]["positions"] == []


def test_demo_entitlements_allow_curated_ticker_and_reject_custom():
    state = {}
    identity = resolve_identity(state)
    assert can_use_ticker(identity, "AAPL")
    assert not can_use_ticker(identity, "NVDA")
    assert not can_view_research_lab(identity)
    assert check_watchlist_limit(identity, 6)
    assert not check_watchlist_limit(identity, 7)
    assert check_position_limit(identity, 10)
    assert not check_position_limit(identity, 11)


def test_demo_forecast_access_is_cache_only(tmp_path):
    with pytest.raises(CachedForecastUnavailable):
        load_demo_forecast("AAPL", repo_root=tmp_path)

    root = tmp_path / ".local" / "forecast_contracts" / "AAPL"
    root.mkdir(parents=True)
    payload = {
        "contract_id": "contract-123",
        "ticker": "AAPL",
        "status": "AVAILABLE",
        "generated_at": "2026-09-21T21:00:00+00:00",
        "forecasts": [],
    }
    (root / "latest.json").write_text(json.dumps(payload), encoding="utf-8")
    assert load_demo_forecast("AAPL", repo_root=tmp_path).contract["contract_id"] == "contract-123"


def test_non_demo_ticker_is_rejected_before_cache_lookup(tmp_path):
    assert not is_demo_ticker("NVDA")
    with pytest.raises(TickerNotEntitled):
        load_demo_forecast("NVDA", repo_root=tmp_path)
