from __future__ import annotations

import numpy as np
import pandas as pd

from market_forecaster.core.feature_store import build_feature_store
from market_forecaster.core.experiment_runner import run_research_experiment


def _frame(n=560):
    rng = np.random.default_rng(17)
    ret = np.zeros(n)
    shocks = rng.normal(0, 0.008, n)
    for i in range(2, n):
        ret[i] = 0.20 * ret[i-1] - 0.08 * ret[i-2] + shocks[i]
    close = 100 * np.exp(np.cumsum(ret))
    return pd.DataFrame({
        "Date": pd.bdate_range("2024-01-01", periods=n),
        "Open": close * (1 + rng.normal(0, 0.001, n)),
        "High": close * 1.01,
        "Low": close * 0.99,
        "Close": close,
        "Volume": rng.integers(500_000, 3_000_000, n),
    })


def test_new_tabular_models_share_protocol():
    features, _ = build_feature_store(_frame(), "TEST")
    result = run_research_experiment(
        features,
        horizons=[1, 5],
        models=["zero_return", "ridge", "elastic_net", "hist_gradient_boosting"],
        n_splits=3,
        test_size=15,
        min_train_size=180,
    )
    assert result["protocol_version"] == "3.7-model-tournament-v1"
    assert result["embargo_rule"] == "max(user_embargo, horizon)"
    models = {row["model"] for row in result["summaries"]}
    assert {"zero_return", "ridge", "elastic_net", "hist_gradient_boosting"} <= models
    for row in result["summaries"]:
        assert row["tournament_rank"] >= 1
        assert "challenger_status" in row


def test_xgboost_reference_fields_when_available():
    features, _ = build_feature_store(_frame(), "TEST")
    result = run_research_experiment(
        features,
        horizons=[5],
        models=["zero_return", "xgboost", "hist_gradient_boosting"],
        n_splits=3,
        test_size=15,
        min_train_size=180,
    )
    xgb_rows = [row for row in result["summaries"] if row["model"] == "xgboost"]
    if xgb_rows:
        assert xgb_rows[0]["challenger_status"] == "REFERENCE"
        challenger = next(row for row in result["summaries"] if row["model"] == "hist_gradient_boosting")
        assert challenger["challenger_status"] in {
            "CHALLENGER_PROMISING", "MIXED_VS_XGB", "NO_LIFT_VS_XGB"
        }
        assert np.isfinite(challenger["improvement_vs_xgb_mae_pct"])


def test_unknown_model_is_reported_not_executed():
    features, _ = build_feature_store(_frame(), "TEST")
    result = run_research_experiment(
        features,
        horizons=[1],
        models=["zero_return", "not_a_real_model"],
        n_splits=3,
        test_size=15,
        min_train_size=180,
    )
    assert result["models_unknown"] == ["not_a_real_model"]
    assert {row["model"] for row in result["summaries"]} == {"zero_return"}
