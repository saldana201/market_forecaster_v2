from __future__ import annotations

import numpy as np
import pandas as pd

from market_forecaster.core.data import infer_forecast_freq
from market_forecaster.core.prophet_model import evaluate_oos, prepare_for_prophet


def _frame(n: int = 140) -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-02", periods=n)
    close = 100 + np.arange(n, dtype=float) * 0.2
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": close - 0.2,
            "High": close + 0.5,
            "Low": close - 0.5,
            "Close": close,
            "Volume": 1_000_000,
            "ret_1d": pd.Series(close).pct_change().to_numpy(),
            "RSI_14": np.linspace(40, 60, n),
            # This deliberately looks like a pattern column. It must not enter Prophet.
            "ascending_triangle": 1.0,
        }
    )


def test_forecast_frequency_equity_vs_crypto():
    assert infer_forecast_freq("AAPL") == "B"
    assert infer_forecast_freq("ETH-USD") == "D"


def test_prepare_for_prophet_lags_technicals_and_excludes_patterns():
    source = _frame(50)
    prepared = prepare_for_prophet(source)
    assert "ascending_triangle" not in prepared.columns
    # RSI at row t must be the source RSI from t-1.
    assert np.isnan(prepared.loc[0, "RSI_14"])
    assert prepared.loc[1, "RSI_14"] == source.loc[0, "RSI_14"]


def test_oos_never_fits_holdout_rows(monkeypatch):
    import market_forecaster.core.prophet_model as pm

    prepared = prepare_for_prophet(_frame())
    seen = []

    def fake_fit(train, future_days=30, use_options=False, future_freq="D", future_dates=None, **kwargs):
        future_dates = pd.DatetimeIndex(pd.to_datetime(list(future_dates)))
        seen.append((pd.Timestamp(train["ds"].max()), pd.Timestamp(future_dates.min())))
        history = pd.DataFrame({"ds": train["ds"], "yhat": train["y"]})
        future = pd.DataFrame({"ds": future_dates, "yhat": float(train["y"].iloc[-1])})
        forecast = pd.concat([history, future], ignore_index=True)
        return object(), forecast, {}

    monkeypatch.setattr(pm, "fit_and_forecast", fake_fit)
    result = evaluate_oos(
        prepared,
        holdout_days=10,
        model_kwargs={"growth": "linear"},
        n_folds=3,
        future_freq="B",
    )
    assert result["evaluation_type"] == "out_of_sample"
    assert result["n_folds"] == 3
    assert seen
    assert all(train_max < test_min for train_max, test_min in seen)
