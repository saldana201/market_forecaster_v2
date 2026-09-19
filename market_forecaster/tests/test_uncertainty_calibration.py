from __future__ import annotations

import copy
import numpy as np

from market_forecaster.core.uncertainty_calibration import (
    _finite_sample_quantile,
    calibrate_current_forecasts,
    prequential_calibration,
)


def _records(folds=4, rows_per_fold=20):
    rows = []
    for fold in range(1, folds + 1):
        for i in range(rows_per_fold):
            pred = -0.02 + 0.04 * (i / max(1, rows_per_fold - 1))
            actual = pred + (0.004 if i % 2 == 0 else -0.003)
            rows.append({
                "horizon": 5,
                "fold": fold,
                "model": "xgboost",
                "origin_date": f"2026-{fold:02d}-{(i % 20) + 1:02d}T00:00:00",
                "target_end_date": f"2026-{fold:02d}-{(i % 20) + 6:02d}T00:00:00",
                "anchor_price": 100.0,
                "predicted_return": pred,
                "actual_return": actual,
                "predicted_price": 100.0 * np.exp(pred),
                "actual_price": 100.0 * np.exp(actual),
            })
    return rows


def test_finite_sample_quantile_is_conservative():
    scores = np.arange(1, 11, dtype=float)
    q = _finite_sample_quantile(scores, 0.90)
    assert q == 10.0


def test_same_fold_outcomes_cannot_change_same_fold_probability_or_interval():
    first = _records(folds=2, rows_per_fold=20)
    changed = copy.deepcopy(first)

    # Rewrite only fold-2 outcomes. Fold-2 calibration must still be identical
    # because it may use fold 1 only.
    for row in changed:
        if row["fold"] == 2:
            row["actual_return"] = -row["actual_return"] * 5.0

    a = prequential_calibration(
        first,
        calibration_window=None,
        min_probability_history=10,
        min_interval_history=10,
    )
    b = prequential_calibration(
        changed,
        calibration_window=None,
        min_probability_history=10,
        min_interval_history=10,
    )

    fold2_a = [r for r in a["evaluation_rows"] if r["fold"] == 2]
    fold2_b = [r for r in b["evaluation_rows"] if r["fold"] == 2]
    assert len(fold2_a) == len(fold2_b) == 20

    for left, right in zip(fold2_a, fold2_b):
        assert np.isclose(left["prob_up"], right["prob_up"], equal_nan=True)
        assert np.isclose(left["lower_return_80"], right["lower_return_80"], equal_nan=True)
        assert np.isclose(left["upper_return_90"], right["upper_return_90"], equal_nan=True)


def test_first_fold_has_no_calibrated_probability_or_interval():
    result = prequential_calibration(
        _records(folds=2, rows_per_fold=20),
        min_probability_history=10,
        min_interval_history=10,
    )
    first = [r for r in result["evaluation_rows"] if r["fold"] == 1]
    assert first
    assert all(np.isnan(r["prob_up"]) for r in first)
    assert all(np.isnan(r["lower_return_80"]) for r in first)


def test_current_forecast_becomes_calibrated_with_sufficient_oos_history():
    history = _records(folds=4, rows_per_fold=20)
    current = [{
        "horizon": 5,
        "origin_date": "2026-09-19T00:00:00",
        "target_date": "2026-09-28T00:00:00",
        "current_price": 100.0,
        "predicted_return": 0.01,
        "predicted_return_pct": (np.exp(0.01) - 1) * 100,
        "predicted_price": 100.0 * np.exp(0.01),
        "train_observations": 500,
    }]
    calibrated = calibrate_current_forecasts(
        current,
        history,
        calibration_window=120,
        min_probability_history=40,
        min_interval_history=40,
    )
    row = calibrated[0]
    assert row["calibration_status"] == "CALIBRATED"
    assert row["calibration_samples"] == 80
    assert 0.0 <= row["prob_up_pct"] <= 100.0
    assert row["lower_price_90"] <= row["lower_price_80"]
    assert row["lower_price_80"] <= row["predicted_price"] <= row["upper_price_80"]
    assert row["upper_price_80"] <= row["upper_price_90"]


def test_rolling_window_limits_calibration_history():
    history = _records(folds=5, rows_per_fold=20)
    current = [{
        "horizon": 5,
        "origin_date": "2026-09-19T00:00:00",
        "target_date": "2026-09-28T00:00:00",
        "current_price": 100.0,
        "predicted_return": 0.0,
        "predicted_return_pct": 0.0,
        "predicted_price": 100.0,
        "train_observations": 500,
    }]
    row = calibrate_current_forecasts(
        current,
        history,
        calibration_window=60,
        min_probability_history=40,
        min_interval_history=40,
    )[0]
    assert row["calibration_samples"] == 60


def test_prequential_summary_reports_empirical_coverage_and_brier():
    result = prequential_calibration(
        _records(folds=5, rows_per_fold=20),
        calibration_window=120,
        min_probability_history=20,
        min_interval_history=20,
    )
    summary = result["summaries"][0]
    assert summary["probability_eval_records"] > 0
    assert np.isfinite(summary["brier_score"])
    assert 0.0 <= summary["coverage_80_pct"] <= 100.0
    assert 0.0 <= summary["coverage_90_pct"] <= 100.0
    assert summary["avg_width_bps_90"] >= summary["avg_width_bps_80"]


def test_probability_mapping_is_bounded_even_with_single_class_history():
    history = _records(folds=3, rows_per_fold=20)
    for row in history:
        row["actual_return"] = abs(row["actual_return"]) + 0.001

    current = [{
        "horizon": 5,
        "origin_date": "2026-09-19T00:00:00",
        "target_date": "2026-09-28T00:00:00",
        "current_price": 100.0,
        "predicted_return": -0.03,
        "predicted_return_pct": (np.exp(-0.03) - 1) * 100,
        "predicted_price": 100.0 * np.exp(-0.03),
        "train_observations": 500,
    }]
    row = calibrate_current_forecasts(
        current,
        history,
        calibration_window=None,
        min_probability_history=20,
        min_interval_history=20,
    )[0]
    assert 0.0 <= row["prob_up_pct"] <= 100.0
