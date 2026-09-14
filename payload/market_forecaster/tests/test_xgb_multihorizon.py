import numpy as np
import pandas as pd
import pytest

from market_forecaster.core.xgb_multihorizon import (
    XGBOOST_AVAILABLE,
    build_xgb_features,
    run_xgb_multihorizon,
)


def _market(n=520):
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2024-01-02", periods=n)
    ret = 0.0004 + 0.008 * rng.standard_normal(n)
    close = 100 * np.exp(np.cumsum(ret))
    return pd.DataFrame({
        "Date": dates,
        "Open": close * (1 + rng.normal(0, 0.002, n)),
        "High": close * (1 + np.abs(rng.normal(0.004, 0.002, n))),
        "Low": close * (1 - np.abs(rng.normal(0.004, 0.002, n))),
        "Close": close,
        "Volume": rng.integers(1_000_000, 6_000_000, n),
    })


def test_features_are_causal_before_future_mutation():
    df = _market()
    base = build_xgb_features(df)
    changed = df.copy()
    changed.loc[changed.index[-40:], "Close"] *= 1.8
    changed.loc[changed.index[-40:], "High"] *= 1.8
    changed.loc[changed.index[-40:], "Low"] *= 1.8
    changed.loc[changed.index[-40:], "Open"] *= 1.8
    mutated = build_xgb_features(changed)
    cols = [c for c in base.columns if c not in {"Date", "Open", "High", "Low", "Close", "Volume"}]
    # Rows well before the mutation boundary must be identical.
    left = base.loc[:430, cols].to_numpy(dtype=float)
    right = mutated.loc[:430, cols].to_numpy(dtype=float)
    assert np.allclose(left, right, equal_nan=True)


@pytest.mark.skipif(not XGBOOST_AVAILABLE, reason="xgboost not installed")
def test_multihorizon_quantiles_are_ordered_and_dates_future():
    df = _market()
    result = run_xgb_multihorizon(
        df, "TEST",
        horizons=(1, 5),
        n_folds=2,
        test_size=14,
        n_estimators=35,
    )
    assert len(result.forecasts) == 2
    as_of = pd.Timestamp(result.as_of)
    for item in result.forecasts:
        assert item.bear_price <= item.base_price <= item.bull_price
        assert item.bear_return_pct <= item.base_return_pct <= item.bull_return_pct
        assert pd.Timestamp(item.target_date) > as_of
        assert item.validation.folds_run == 2


@pytest.mark.skipif(not XGBOOST_AVAILABLE, reason="xgboost not installed")
def test_multihorizon_result_serializes():
    result = run_xgb_multihorizon(
        _market(), "TEST",
        horizons=(1,), n_folds=2, test_size=12, n_estimators=30,
    )
    payload = result.to_dict()
    assert payload["ticker"] == "TEST"
    assert payload["forecasts"][0]["horizon"] == 1
    assert payload["config"]["target"] == "cumulative_log_return"
