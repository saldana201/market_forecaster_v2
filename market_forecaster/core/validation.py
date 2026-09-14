"""Shared production validation primitives.

The forecasting application uses expanding-window, chronological validation only.
No random train/test shuffling is allowed for market time series.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np


@dataclass(frozen=True)
class TimeSeriesSplit:
    fold: int
    train_start: int
    train_end: int  # exclusive
    test_start: int
    test_end: int   # exclusive
    gap: int

    @property
    def train_size(self) -> int:
        return self.train_end - self.train_start

    @property
    def test_size(self) -> int:
        return self.test_end - self.test_start


def expanding_window_splits(
    n_samples: int,
    *,
    test_size: int,
    n_splits: int,
    gap: int = 1,
    min_train_size: int = 120,
) -> Iterator[TimeSeriesSplit]:
    """Yield chronological expanding-window splits with an embargo gap.

    The returned folds run oldest -> newest. The `gap` rows immediately before
    each test window are excluded from training. This makes the validation
    contract explicit and gives future label/feature pipelines room to avoid
    boundary leakage.
    """
    if n_samples <= 0:
        return
    test_size = max(1, int(test_size))
    n_splits = max(1, int(n_splits))
    gap = max(0, int(gap))
    min_train_size = max(1, int(min_train_size))

    candidate: list[TimeSeriesSplit] = []
    for reverse_fold in range(n_splits - 1, -1, -1):
        test_end = n_samples - reverse_fold * test_size
        test_start = test_end - test_size
        train_end = test_start - gap
        if test_start < 0 or train_end < min_train_size:
            continue
        candidate.append(
            TimeSeriesSplit(
                fold=len(candidate) + 1,
                train_start=0,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                gap=gap,
            )
        )
    yield from candidate


def forecast_metrics(
    train_y: np.ndarray,
    actual: np.ndarray,
    predicted: np.ndarray,
) -> dict[str, float]:
    """Compute scale, percentage, and directional forecast metrics."""
    train_y = np.asarray(train_y, dtype=float)
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    valid = np.isfinite(actual) & np.isfinite(predicted)
    actual, predicted = actual[valid], predicted[valid]
    if not len(actual):
        return {
            "mae": np.nan,
            "rmse": np.nan,
            "mape": np.nan,
            "smape": np.nan,
            "mase": np.nan,
            "directional_accuracy": np.nan,
            "terminal_direction_correct": np.nan,
        }

    err = actual - predicted
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err ** 2)))

    nz = np.where(actual == 0, np.nan, actual)
    mape = float(np.nanmean(np.abs(err / nz)) * 100)
    denom = np.where((np.abs(actual) + np.abs(predicted)) == 0, np.nan,
                     (np.abs(actual) + np.abs(predicted)) / 2)
    smape = float(np.nanmean(np.abs(err) / denom) * 100)

    train_diff = np.abs(np.diff(train_y[np.isfinite(train_y)]))
    naive_scale = float(np.mean(train_diff)) if len(train_diff) else np.nan
    mase = float(mae / naive_scale) if np.isfinite(naive_scale) and naive_scale > 0 else np.nan

    anchor = float(train_y[np.isfinite(train_y)][-1])
    actual_path = np.concatenate([[anchor], actual])
    predicted_path = np.concatenate([[anchor], predicted])
    actual_dir = np.sign(np.diff(actual_path))
    pred_dir = np.sign(np.diff(predicted_path))
    directional_accuracy = float(np.mean(actual_dir == pred_dir) * 100)

    terminal_actual = np.sign(actual[-1] - anchor)
    terminal_pred = np.sign(predicted[-1] - anchor)
    terminal_correct = float(terminal_actual == terminal_pred)

    return {
        "mae": mae,
        "rmse": rmse,
        "mape": mape,
        "smape": smape,
        "mase": mase,
        "directional_accuracy": directional_accuracy,
        "terminal_direction_correct": terminal_correct,
    }


def paired_fold_improvement(
    candidate: np.ndarray,
    baseline: np.ndarray,
    *,
    seed: int = 42,
    bootstrap_samples: int = 2000,
) -> dict[str, float]:
    """Paired bootstrap of fold-level error improvement vs a baseline.

    Positive values mean the candidate has lower error than the baseline.
    The output is descriptive evidence, not a statistical guarantee.
    """
    candidate = np.asarray(candidate, dtype=float)
    baseline = np.asarray(baseline, dtype=float)
    valid = np.isfinite(candidate) & np.isfinite(baseline) & (baseline > 0)
    candidate, baseline = candidate[valid], baseline[valid]
    if not len(candidate):
        return {"mean_improvement_pct": np.nan, "ci_low_pct": np.nan, "ci_high_pct": np.nan}

    improvements = (baseline - candidate) / baseline * 100.0
    if len(improvements) == 1:
        value = float(improvements[0])
        return {"mean_improvement_pct": value, "ci_low_pct": value, "ci_high_pct": value}

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(improvements), size=(max(100, bootstrap_samples), len(improvements)))
    samples = improvements[idx].mean(axis=1)
    return {
        "mean_improvement_pct": float(improvements.mean()),
        "ci_low_pct": float(np.quantile(samples, 0.025)),
        "ci_high_pct": float(np.quantile(samples, 0.975)),
    }
