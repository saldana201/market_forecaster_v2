from __future__ import annotations
import numpy as np
import pandas as pd

from market_forecaster.core.market_context import (
    align_context_source,
    build_market_context,
    build_source_features,
)


def _market(n=80, start="2026-01-01", scale=100.0):
    rng = np.random.default_rng(5)
    close = scale * np.exp(np.cumsum(rng.normal(0.0002, 0.01, n)))
    return pd.DataFrame({
        "Date": pd.bdate_range(start, periods=n),
        "Close": close,
    })


def _base(n=80):
    df = _market(n)
    out = pd.DataFrame({
        "Date": df["Date"],
        "Close": df["Close"],
        "feature_asof": df["Date"],
        "feature_schema_version": "test-v1",
        "logret_5": np.log(df["Close"]).diff(5),
        "target_log_return_5d": np.log(df["Close"].shift(-5) / df["Close"]),
        "target_end_date_5d": df["Date"].shift(-5),
    })
    return out


def test_source_feature_is_causal_against_future_mutation():
    source = _market(100)
    original = build_source_features(source, prefix="ctx_test_asset")
    changed = source.copy()
    changed.loc[70:, "Close"] *= 5
    modified = build_source_features(changed, prefix="ctx_test_asset")
    cols = [c for c in original.columns if c != "source_date"]
    for col in cols:
        left = original.loc[60, col]
        right = modified.loc[60, col]
        assert np.isclose(left, right, equal_nan=True), col


def test_alignment_is_backward_only():
    target = pd.DataFrame({
        "Date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
        "Close": [10, 11, 12],
    })
    source = pd.DataFrame({
        "source_date": pd.to_datetime(["2026-01-05", "2026-01-07"]),
        "ctx_demo_ret_1": [1.0, 3.0],
    })
    aligned = align_context_source(
        target, source, age_column="ctx_demo_age_days", max_staleness_days=7
    )
    assert aligned.loc[1, "ctx_demo_ret_1"] == 1.0
    assert aligned.loc[1, "ctx_demo_age_days"] == 1.0


def test_same_target_symbol_is_skipped():
    calls = []
    def fetcher(symbol, period, interval):
        calls.append(symbol)
        return _market()
    _, registry = build_market_context(
        _base(),
        "SPY",
        families=["broad_market"],
        fetcher=fetcher,
    )
    assert "SPY" not in calls
    assert "QQQ" in calls
    assert registry["broad_market"]["sources_skipped"][0]["reason"] == "same_as_target"


def test_context_registry_never_marks_target_columns_as_features():
    frames = {
        "SPY": _market(scale=100),
        "QQQ": _market(scale=200),
    }
    def fetcher(symbol, period, interval):
        return frames.get(symbol, pd.DataFrame())
    enriched, registry = build_market_context(
        _base(),
        "TEST",
        families=["broad_market"],
        fetcher=fetcher,
    )
    assert registry["broad_market"]["available"]
    assert all(not c.startswith("target_") for c in registry["broad_market"]["columns"])
    assert any(c.startswith("ctx_broad_market_") for c in enriched.columns)
