from __future__ import annotations

import numpy as np
import pandas as pd

from market_forecaster.core import model_tournament as mt


def test_registry_contains_expected_challengers():
    registry = {row["name"]: row for row in mt.model_registry()}
    for name in [
        "zero_return", "ridge", "elastic_net", "random_forest",
        "hist_gradient_boosting", "xgboost", "lightgbm", "catboost",
        "lstm", "tcn", "transformer",
    ]:
        assert name in registry
    assert registry["xgboost"]["family"] == "boosting"
    assert registry["lstm"]["sequence"] is True


def test_dependency_free_tabular_models_build():
    for name in ["ridge", "elastic_net", "random_forest", "hist_gradient_boosting"]:
        assert mt.build_tabular_model(name, 42) is not None


def test_torch_sequence_first_prediction_is_future_feature_invariant():
    if not mt.TORCH_AVAILABLE:
        return
    rng = np.random.default_rng(5)
    X = pd.DataFrame(rng.normal(size=(260, 6)))
    y = pd.Series(0.01 * X[0].shift(1).fillna(0) + rng.normal(0, 0.002, 260))

    pred1, kept1 = mt.fit_predict_sequence(
        "lstm", X, y,
        train_start=0, train_end=210,
        test_start=230, test_end=235,
        lookback=20, epochs=1, batch_size=64, random_state=7,
    )

    changed = X.copy()
    changed.iloc[231:, :] += 1000.0
    pred2, kept2 = mt.fit_predict_sequence(
        "lstm", changed, y,
        train_start=0, train_end=210,
        test_start=230, test_end=235,
        lookback=20, epochs=1, batch_size=64, random_state=7,
    )

    assert kept1.tolist() == kept2.tolist() == [230, 231, 232, 233, 234]
    assert np.isfinite(pred1).all()
    assert np.isclose(pred1[0], pred2[0], atol=1e-7)
