from __future__ import annotations

import numpy as np
import pandas as pd

from market_forecaster.core.validation import expanding_window_splits, forecast_metrics


def test_expanding_window_split_has_gap_and_no_overlap():
    splits = list(expanding_window_splits(300, test_size=20, n_splits=4, gap=3, min_train_size=100))
    assert len(splits) == 4
    for split in splits:
        assert split.train_end + 3 == split.test_start
        assert split.train_end <= split.test_start
        assert split.test_size == 20
    assert [s.test_start for s in splits] == sorted(s.test_start for s in splits)


def test_directional_accuracy_uses_training_anchor():
    train = np.array([100.0, 101.0, 102.0])
    actual = np.array([103.0, 104.0])
    pred = np.array([103.5, 105.0])
    metrics = forecast_metrics(train, actual, pred)
    assert metrics["directional_accuracy"] == 100.0
    assert metrics["terminal_direction_correct"] == 1.0


def test_model_zoo_keeps_naive_baseline(monkeypatch):
    import market_forecaster.core.model_zoo as mz

    n = 220
    dates = pd.bdate_range("2025-01-02", periods=n)
    close = 100 + np.linspace(0, 20, n)
    df = pd.DataFrame({"Date": dates, "Close": close})

    # Keep the unit test light/deterministic: disable optional expensive models.
    monkeypatch.setattr(mz, "PROPHET_AVAILABLE", False)
    monkeypatch.setattr(mz, "ARIMA_AVAILABLE", False)
    result = mz.run_model_zoo(df, test_size=10, n_folds=3, gap=1)

    assert "naive" in set(result.leaderboard["model"])
    assert {"ridge", "random_forest"}.intersection(set(result.leaderboard["model"]))
    assert result.config["n_folds_run"] == 3
    assert set(result.leaderboard["production_gate"]).issubset({"PASS", "HOLD", "BASELINE"})
