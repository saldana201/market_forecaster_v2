from __future__ import annotations

import numpy as np
import pandas as pd

from market_forecaster.core.regime import (
    RegimeSnapshot,
    classify_regime,
    derive_regime_routing,
    ensemble_weight_names,
)
from market_forecaster.core.volatility import forecast_volatility


def _market_frame(n: int = 320, seed: int = 7, drift: float = 0.0008, sigma: float = 0.006) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ret = drift + rng.normal(0, sigma, n)
    close = 100 * np.exp(np.cumsum(ret))
    spread = np.maximum(0.002, np.abs(rng.normal(0.008, 0.002, n)))
    return pd.DataFrame({
        "Date": pd.bdate_range("2025-01-02", periods=n),
        "Close": close,
        "High": close * (1 + spread),
        "Low": close * (1 - spread),
    })


def test_regime_classifier_returns_causal_state():
    df = _market_frame()
    snapshot = classify_regime(df)
    assert snapshot.trend_state in {"UP", "DOWN", "RANGE"}
    assert snapshot.volatility_state in {"LOW", "NORMAL", "HIGH", "EXTREME"}
    assert snapshot.composite in {"TREND_UP", "TREND_DOWN", "RANGE", "HIGH_VOL", "STRESS"}
    assert snapshot.realized_vol_20 > 0
    assert 0 <= snapshot.volatility_percentile <= 1


def test_volatility_forecast_is_positive_for_supported_horizons():
    df = _market_frame(n=420)
    result = forecast_volatility(df)
    assert set(result.forecasts) == {1, 5, 20}
    assert result.current_annualized > 0
    assert all(np.isfinite(v) and v > 0 for v in result.forecasts.values())


def test_regime_routing_uses_only_passed_models_and_matching_folds():
    snapshot = RegimeSnapshot(
        composite="HIGH_VOL",
        trend_state="RANGE",
        volatility_state="HIGH",
        realized_vol_20=0.4,
        realized_vol_60=0.3,
        volatility_percentile=0.8,
        atr_pct_14=0.02,
        return_5d=0.01,
        return_20d=0.02,
        drawdown_252=-0.05,
        as_of=pd.Timestamp("2026-09-01"),
    )
    leaderboard = pd.DataFrame([
        {"model": "ridge", "production_gate": "PASS"},
        {"model": "random_forest", "production_gate": "PASS"},
        {"model": "arima", "production_gate": "HOLD"},
        {"model": "prophet", "production_gate": "PASS"},
    ])
    folds = pd.DataFrame([
        {"fold": 1, "model": "ridge", "smape": 4.0, "regime": "HIGH_VOL", "volatility_state": "HIGH"},
        {"fold": 2, "model": "ridge", "smape": 5.0, "regime": "HIGH_VOL", "volatility_state": "HIGH"},
        {"fold": 1, "model": "random_forest", "smape": 3.0, "regime": "HIGH_VOL", "volatility_state": "HIGH"},
        {"fold": 2, "model": "random_forest", "smape": 3.5, "regime": "HIGH_VOL", "volatility_state": "HIGH"},
        {"fold": 1, "model": "arima", "smape": 2.0, "regime": "HIGH_VOL", "volatility_state": "HIGH"},
        {"fold": 2, "model": "arima", "smape": 2.0, "regime": "HIGH_VOL", "volatility_state": "HIGH"},
    ])
    routing = derive_regime_routing(folds, leaderboard, snapshot)
    assert routing.active
    assert set(routing.weights) == {"ridge", "random_forest"}
    assert routing.weights["random_forest"] > routing.weights["ridge"]
    translated = ensemble_weight_names(routing.weights)
    assert set(translated) == {"ridge", "rf"}
    assert abs(sum(translated.values()) - 1.0) < 1e-9
