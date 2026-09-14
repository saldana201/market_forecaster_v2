from __future__ import annotations

import numpy as np
import pandas as pd

from market_forecaster.core.historical_options import (
    align_options_with_market,
    evaluate_options_history,
    flatten_options_history,
)


def _snapshot(ts, score=0.2, ticker="TEST"):
    return {
        "available": True,
        "ticker": ticker,
        "as_of_utc": pd.Timestamp(ts).isoformat(),
        "spot": 100.0,
        "options_signal_score": score,
        "directional_pressure_score": score,
        "pressure_coverage": 0.6,
        "gamma_balance_score": score / 2,
        "atm_iv": 0.25,
        "skew_25d": -0.05 * score,
        "iv_term_structure_slope": 0.02,
        "put_call_volume_ratio": 0.9,
        "put_call_oi_ratio": 0.95,
        "maturity_buckets": [
            {
                "bucket": "0-7d",
                "directional_pressure_score": score,
                "skew_25d": -0.04 * score,
                "signed_gamma_proxy": score * 1000,
                "call_gamma_dollar_1pct": 2000,
                "put_gamma_dollar_1pct": 1000,
            },
            {
                "bucket": "8-30d",
                "directional_pressure_score": score * 0.8,
                "skew_25d": -0.03 * score,
                "signed_gamma_proxy": score * 800,
                "call_gamma_dollar_1pct": 1600,
                "put_gamma_dollar_1pct": 900,
            },
        ],
    }


def test_same_session_snapshots_are_deduplicated():
    base = pd.Timestamp("2026-01-05 15:00", tz="UTC")
    frame = flatten_options_history([_snapshot(base, 0.1), _snapshot(base + pd.Timedelta(hours=2), 0.8)])
    assert len(frame) == 1
    assert frame.iloc[0]["options_signal_score"] == 0.8


def test_alignment_uses_strictly_next_market_session_open():
    dates = pd.bdate_range("2026-01-05", periods=8)
    stock = pd.DataFrame({"Date": dates, "Open": np.arange(100, 108, dtype=float), "Close": np.arange(101, 109, dtype=float)})
    snap = flatten_options_history([_snapshot(pd.Timestamp("2026-01-05 18:00", tz="UTC"), 0.2)])
    aligned = align_options_with_market(snap, stock, horizons=(1, 5))
    assert len(aligned) == 1
    assert pd.Timestamp(aligned.iloc[0]["entry_date"]) == dates[1]
    assert aligned.iloc[0]["entry_open"] == 101.0
    expected = stock.iloc[1]["Close"] / stock.iloc[1]["Open"] - 1.0
    assert abs(aligned.iloc[0]["target_return_1"] - expected) < 1e-12


def test_insufficient_real_sessions_stays_collecting():
    dates = pd.bdate_range("2026-01-05", periods=40)
    history = [_snapshot(d.tz_localize("UTC") + pd.Timedelta(hours=18), 0.2) for d in dates[:20]]
    stock = pd.DataFrame({"Date": dates, "Open": 100.0, "Close": 101.0})
    result = evaluate_options_history(history, stock, min_unique_sessions=30)
    assert result["status"] == "COLLECTING"
    assert result["routing_effect"] == "NONE_IN_2_7"


def test_predictive_options_signal_can_pass_oos_gate():
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2026-01-02", periods=115)
    scores = rng.choice([-1.0, -0.7, -0.4, 0.4, 0.7, 1.0], size=100)
    history = []
    for i, score in enumerate(scores):
        history.append(_snapshot(dates[i].tz_localize("UTC") + pd.Timedelta(hours=18), float(score)))
    opens = np.full(len(dates), 100.0)
    closes = np.full(len(dates), 100.0)
    for i, score in enumerate(scores):
        if i + 1 < len(closes):
            closes[i + 1] = 100.0 * (1.0 + 0.02 * score + rng.normal(0, 0.001))
    stock = pd.DataFrame({"Date": dates, "Open": opens, "Close": closes})
    result = evaluate_options_history(history, stock, horizons=(1,), min_unique_sessions=60, n_folds=3, min_train=30)
    assert result["status"] == "READY"
    row = result["horizons"][0]
    assert row["gate"] == "PASS"
    assert row["improvement_pct"] > 3.0
    assert row["directional_accuracy"] >= 52.0
