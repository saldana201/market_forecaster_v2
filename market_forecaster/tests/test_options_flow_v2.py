from datetime import datetime, timezone

import pandas as pd

from market_forecaster.core.options_flow_v2 import (
    analyze_options_frames,
    derive_options_regime_overlay,
    load_options_history,
    option_greeks,
    persist_options_snapshot,
)


def _frame(rows):
    return pd.DataFrame(rows)


def _chains(call_last=1.19, put_last=1.19):
    calls_front = _frame([
        {"strike": 100, "volume": 800, "openInterest": 200, "impliedVolatility": 0.30, "bid": 1.00, "ask": 1.20, "lastPrice": call_last},
        {"strike": 110, "volume": 80, "openInterest": 300, "impliedVolatility": 0.28, "bid": 0.45, "ask": 0.60, "lastPrice": 0.52},
    ])
    puts_front = _frame([
        {"strike": 100, "volume": 150, "openInterest": 250, "impliedVolatility": 0.34, "bid": 1.00, "ask": 1.20, "lastPrice": put_last},
        {"strike": 90, "volume": 60, "openInterest": 350, "impliedVolatility": 0.42, "bid": 0.40, "ask": 0.55, "lastPrice": 0.47},
    ])
    calls_back = _frame([
        {"strike": 100, "volume": 50, "openInterest": 500, "impliedVolatility": 0.36, "bid": 3.0, "ask": 3.3, "lastPrice": 3.15},
    ])
    puts_back = _frame([
        {"strike": 100, "volume": 55, "openInterest": 480, "impliedVolatility": 0.38, "bid": 3.0, "ask": 3.3, "lastPrice": 3.15},
    ])
    return [
        {"expiry": "2026-09-20", "calls": calls_front, "puts": puts_front},
        {"expiry": "2026-11-15", "calls": calls_back, "puts": puts_back},
    ]


def test_black_scholes_greeks_have_expected_signs():
    call = option_greeks(100, 100, 30 / 365, 0.30, "CALL")
    put = option_greeks(100, 100, 30 / 365, 0.30, "PUT")
    assert 0 < call.delta < 1
    assert -1 < put.delta < 0
    assert call.gamma > 0
    assert abs(call.gamma - put.gamma) < 1e-12


def test_analyzer_builds_surface_buckets_and_bullish_pressure():
    result = analyze_options_frames(
        _chains(call_last=1.19, put_last=1.10),
        spot=100,
        ticker="TEST",
        as_of=datetime(2026, 9, 14, tzinfo=timezone.utc),
    )
    assert result["available"] is True
    assert result["contracts_analyzed"] >= 6
    assert len(result["maturity_buckets"]) == 5
    assert result["atm_iv"] is not None
    assert result["directional_pressure_score"] > 0
    assert -1 <= result["gamma_balance_score"] <= 1


def test_buyer_put_pressure_is_bearish():
    chains = _chains(call_last=1.10, put_last=1.19)
    # Suppress call-side classified volume and make front puts quote-side buyers.
    chains[0]["calls"]["lastPrice"] = 1.10
    chains[0]["puts"]["lastPrice"] = 1.19
    result = analyze_options_frames(
        chains,
        spot=100,
        ticker="TEST",
        as_of=datetime(2026, 9, 14, tzinfo=timezone.utc),
    )
    assert result["directional_pressure_score"] < 0


def test_persistence_records_only_observed_snapshots(tmp_path):
    result = analyze_options_frames(
        _chains(), spot=100, ticker="SPY",
        as_of=datetime(2026, 9, 14, tzinfo=timezone.utc),
    )
    path = persist_options_snapshot(result, tmp_path)
    assert path is not None and path.exists()
    rows = load_options_history("SPY", base_dir=tmp_path)
    assert len(rows) == 1
    overlay = derive_options_regime_overlay(rows[0], "TREND_UP")
    assert overlay["routing_effect"] == "DISPLAY_AND_SIGNAL_ONLY"
