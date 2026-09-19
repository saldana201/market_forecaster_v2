"""Probability calibration and rolling conformal-style uncertainty for Market Forecaster 3.9.

Point forecasts reuse the existing 3.7 model adapters and 3.6/3.8 causal feature
schema. OOS probabilities and interval widths are calibrated only from earlier
OOS folds. The current fold never calibrates itself.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from market_forecaster.core.feature_store import (
    assert_point_in_time_integrity,
    research_feature_columns,
)
from market_forecaster.core.model_tournament import (
    build_tabular_model,
    fit_predict_sequence,
    is_model_available,
    is_sequence_model,
    model_status_map,
)
from market_forecaster.core.targets import DEFAULT_RESEARCH_HORIZONS, target_columns
from market_forecaster.core.validation import expanding_window_splits

DEFAULT_COVERAGE_LEVELS = (0.80, 0.90)


def _clean_levels(levels: Iterable[float]) -> list[float]:
    values = sorted({float(x) for x in levels if 0.5 < float(x) < 1.0})
    return values or list(DEFAULT_COVERAGE_LEVELS)


def _future_target_date(last_date: pd.Timestamp, horizon: int, ticker: str) -> str:
    if str(ticker or "").upper().strip().endswith("-USD"):
        target = pd.Timestamp(last_date) + pd.Timedelta(days=int(horizon))
    else:
        target = pd.Timestamp(last_date) + pd.offsets.BDay(int(horizon))
    return pd.Timestamp(target).isoformat()


def _validate_no_label_overlap(
    frame: pd.DataFrame,
    horizon: int,
    train_end_exclusive: int,
    test_start: int,
) -> None:
    cols = target_columns(horizon)
    if train_end_exclusive <= 0 or test_start >= len(frame):
        return
    train_target_end = pd.to_datetime(
        frame.iloc[train_end_exclusive - 1][cols["end_date"]],
        errors="coerce",
    )
    test_start_date = pd.to_datetime(frame.iloc[test_start]["Date"], errors="coerce")
    if (
        pd.notna(train_target_end)
        and pd.notna(test_start_date)
        and train_target_end >= test_start_date
    ):
        raise RuntimeError(
            f"Target overlap detected for {horizon}D: "
            f"last train label ends {train_target_end}, test starts {test_start_date}"
        )


def _finite_sample_quantile(scores: np.ndarray, coverage: float) -> float:
    scores = np.asarray(scores, dtype=float)
    scores = scores[np.isfinite(scores)]
    if not len(scores):
        return float("nan")
    n = len(scores)
    q = min(1.0, np.ceil((n + 1) * float(coverage)) / n)
    try:
        return float(np.quantile(scores, q, method="higher"))
    except TypeError:
        return float(np.quantile(scores, q, interpolation="higher"))


def _history_window(frame: pd.DataFrame, window: int | None) -> pd.DataFrame:
    ordered = frame.sort_values(["fold", "origin_date"]).reset_index(drop=True)
    if window is None or int(window) <= 0:
        return ordered
    return ordered.tail(int(window)).reset_index(drop=True)


def _fit_probability_model(history: pd.DataFrame):
    hist = history.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["predicted_return", "actual_return"]
    )
    if hist.empty:
        return None, np.nan
    y = (hist["actual_return"].to_numpy(dtype=float) > 0).astype(int)
    fallback = float((y.sum() + 1.0) / (len(y) + 2.0))
    if len(hist) < 10 or len(np.unique(y)) < 2:
        return None, fallback
    X = hist[["predicted_return"]].to_numpy(dtype=float)
    model = Pipeline([
        ("scale", StandardScaler()),
        ("logit", LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)),
    ])
    model.fit(X, y)
    return model, fallback


def _predict_probability(model, fallback: float, predicted_return: np.ndarray) -> np.ndarray:
    pred = np.asarray(predicted_return, dtype=float)
    if model is None:
        return np.full(len(pred), float(fallback), dtype=float)
    probs = model.predict_proba(pred.reshape(-1, 1))[:, 1]
    return np.clip(np.asarray(probs, dtype=float), 0.0, 1.0)


def _ece(probabilities: np.ndarray, outcomes: np.ndarray, bins: int = 5) -> float:
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    valid = np.isfinite(p) & np.isfinite(y)
    p, y = p[valid], y[valid]
    if not len(p):
        return float("nan")
    edges = np.linspace(0.0, 1.0, int(bins) + 1)
    total = len(p)
    error = 0.0
    for i in range(len(edges) - 1):
        if i == len(edges) - 2:
            mask = (p >= edges[i]) & (p <= edges[i + 1])
        else:
            mask = (p >= edges[i]) & (p < edges[i + 1])
        if not mask.any():
            continue
        error += float(mask.sum() / total) * abs(float(p[mask].mean()) - float(y[mask].mean()))
    return float(error)


def collect_oos_predictions(
    feature_frame: pd.DataFrame,
    *,
    model: str = "xgboost",
    horizons: Iterable[int] = DEFAULT_RESEARCH_HORIZONS,
    n_splits: int = 6,
    test_size: int = 20,
    min_train_size: int = 180,
    embargo: int = 0,
    random_state: int = 42,
    sequence_lookback: int = 20,
    deep_epochs: int = 15,
) -> dict:
    pit = assert_point_in_time_integrity(feature_frame)
    if pit["status"] != "PASS":
        raise ValueError(f"Point-in-time integrity failed: {pit['problems']}")

    model = str(model).strip().lower()
    registry = model_status_map()
    if model not in registry:
        raise ValueError(f"Unknown research model: {model}")
    if not is_model_available(model):
        raise RuntimeError(f"Research model is unavailable: {model}")
    if model in {"zero_return", "historical_mean"}:
        raise ValueError("3.9 calibration requires a fitted forecasting model, not a baseline")

    features = research_feature_columns(feature_frame)
    if not features:
        raise ValueError("No research features are available")

    records = []
    errors = []

    for horizon in sorted({int(h) for h in horizons if int(h) > 0}):
        cols = target_columns(horizon)
        required = [cols["log_return"], cols["end_date"]]
        if any(c not in feature_frame.columns for c in required):
            continue

        work = feature_frame[
            ["Date", "Close", cols["log_return"], cols["end_date"], *features]
        ].copy()
        work = work.dropna(
            subset=["Date", "Close", cols["log_return"], cols["end_date"]]
        ).reset_index(drop=True)

        if len(work) < max(int(min_train_size) + int(test_size) + horizon, 60):
            continue

        X = work[features].replace([np.inf, -np.inf], np.nan)
        y = pd.to_numeric(work[cols["log_return"]], errors="coerce")
        anchors = pd.to_numeric(work["Close"], errors="coerce")
        purge_gap = max(int(embargo), int(horizon))
        splits = list(expanding_window_splits(
            len(work),
            test_size=int(test_size),
            n_splits=int(n_splits),
            gap=purge_gap,
            min_train_size=max(int(min_train_size), 8 * horizon, int(sequence_lookback) + 40),
        ))

        for split in splits:
            _validate_no_label_overlap(work, horizon, split.train_end, split.test_start)
            try:
                if is_sequence_model(model):
                    pred, kept = fit_predict_sequence(
                        model,
                        X,
                        y,
                        train_start=split.train_start,
                        train_end=split.train_end,
                        test_start=split.test_start,
                        test_end=split.test_end,
                        lookback=int(sequence_lookback),
                        epochs=int(deep_epochs),
                        random_state=int(random_state + horizon + split.fold),
                    )
                    eval_indices = np.asarray(kept, dtype=int)
                else:
                    fitted = build_tabular_model(
                        model,
                        int(random_state + horizon + split.fold),
                    )
                    if fitted is None:
                        raise RuntimeError(f"Could not build model: {model}")
                    fitted.fit(
                        X.iloc[split.train_start:split.train_end],
                        y.iloc[split.train_start:split.train_end],
                    )
                    eval_indices = np.arange(split.test_start, split.test_end, dtype=int)
                    pred = np.asarray(fitted.predict(X.iloc[eval_indices]), dtype=float)

                actual = y.iloc[eval_indices].to_numpy(dtype=float)
                anchor = anchors.iloc[eval_indices].to_numpy(dtype=float)
                for idx, p, a, price in zip(eval_indices, pred, actual, anchor):
                    if not (np.isfinite(p) and np.isfinite(a) and np.isfinite(price) and price > 0):
                        continue
                    records.append({
                        "horizon": int(horizon),
                        "fold": int(split.fold),
                        "model": model,
                        "origin_date": pd.Timestamp(work.iloc[int(idx)]["Date"]).isoformat(),
                        "target_end_date": pd.Timestamp(work.iloc[int(idx)][cols["end_date"]]).isoformat(),
                        "anchor_price": float(price),
                        "predicted_return": float(p),
                        "actual_return": float(a),
                        "predicted_price": float(price * np.exp(p)),
                        "actual_price": float(price * np.exp(a)),
                    })
            except Exception as exc:
                errors.append({
                    "horizon": int(horizon),
                    "fold": int(split.fold),
                    "model": model,
                    "error": str(exc),
                })

    return {
        "model": model,
        "feature_count": len(features),
        "feature_schema_version": pit.get("schema_version"),
        "records": records,
        "model_errors": errors,
        "fold_rule": "expanding-window; gap=max(user_embargo,horizon)",
    }


def prequential_calibration(
    records: list[dict],
    *,
    coverage_levels: Iterable[float] = DEFAULT_COVERAGE_LEVELS,
    calibration_window: int | None = 120,
    min_probability_history: int = 40,
    min_interval_history: int = 40,
) -> dict:
    """Evaluate calibration using only OOS history from earlier folds."""
    df = pd.DataFrame(records)
    levels = _clean_levels(coverage_levels)
    if df.empty:
        return {"evaluation_rows": [], "summaries": [], "coverage_levels": levels}

    evaluation_rows = []
    summaries = []

    for horizon in sorted(df["horizon"].unique()):
        hdf = df[df["horizon"] == horizon].copy()
        hdf["origin_date"] = pd.to_datetime(hdf["origin_date"], errors="coerce")
        hdf = hdf.sort_values(["fold", "origin_date"]).reset_index(drop=True)
        history = hdf.iloc[0:0].copy()

        for fold in sorted(hdf["fold"].unique()):
            current = hdf[hdf["fold"] == fold].copy()
            hist = _history_window(history, calibration_window)

            probability_ready = len(hist) >= int(min_probability_history)
            interval_ready = len(hist) >= int(min_interval_history)

            probabilities = np.full(len(current), np.nan, dtype=float)
            if probability_ready:
                prob_model, fallback = _fit_probability_model(hist)
                probabilities = _predict_probability(
                    prob_model,
                    fallback,
                    current["predicted_return"].to_numpy(dtype=float),
                )

            interval_quantiles = {}
            if interval_ready:
                residuals = np.abs(
                    hist["actual_return"].to_numpy(dtype=float)
                    - hist["predicted_return"].to_numpy(dtype=float)
                )
                for level in levels:
                    interval_quantiles[level] = _finite_sample_quantile(residuals, level)

            for pos, (_, row) in enumerate(current.iterrows()):
                out = dict(row)
                out["prob_up"] = float(probabilities[pos]) if np.isfinite(probabilities[pos]) else np.nan
                out["probability_history"] = int(len(hist)) if probability_ready else 0
                out["interval_history"] = int(len(hist)) if interval_ready else 0

                pred = float(row["predicted_return"])
                actual = float(row["actual_return"])
                for level in levels:
                    label = int(round(level * 100))
                    q = interval_quantiles.get(level, np.nan)
                    low = pred - q if np.isfinite(q) else np.nan
                    high = pred + q if np.isfinite(q) else np.nan
                    out[f"lower_return_{label}"] = low
                    out[f"upper_return_{label}"] = high
                    out[f"covered_{label}"] = (
                        bool(low <= actual <= high)
                        if np.isfinite(low) and np.isfinite(high)
                        else None
                    )
                    out[f"width_bps_{label}"] = (
                        float((high - low) * 10000.0)
                        if np.isfinite(low) and np.isfinite(high)
                        else np.nan
                    )
                evaluation_rows.append(out)

            # Current fold becomes calibration history only after evaluation.
            history = pd.concat([history, current], ignore_index=True)

        eval_h = pd.DataFrame(
            [row for row in evaluation_rows if int(row["horizon"]) == int(horizon)]
        )
        prob_eval = eval_h.dropna(subset=["prob_up"]) if not eval_h.empty else pd.DataFrame()

        if not prob_eval.empty:
            outcomes = (prob_eval["actual_return"].to_numpy(dtype=float) > 0).astype(float)
            probs = prob_eval["prob_up"].to_numpy(dtype=float)
            brier = float(np.mean((probs - outcomes) ** 2))
            ece = _ece(probs, outcomes)
        else:
            brier = np.nan
            ece = np.nan

        summary = {
            "horizon": int(horizon),
            "oos_records": int(len(hdf)),
            "probability_eval_records": int(len(prob_eval)),
            "brier_score": brier,
            "brier_skill_vs_50_pct": (
                float((1.0 - brier / 0.25) * 100.0)
                if np.isfinite(brier) else np.nan
            ),
            "expected_calibration_error": ece,
        }

        for level in levels:
            label = int(round(level * 100))
            covered = (
                eval_h[f"covered_{label}"].dropna()
                if not eval_h.empty else pd.Series(dtype=bool)
            )
            widths = (
                pd.to_numeric(eval_h[f"width_bps_{label}"], errors="coerce").dropna()
                if not eval_h.empty else pd.Series(dtype=float)
            )
            summary[f"coverage_{label}_pct"] = (
                float(covered.astype(float).mean() * 100.0)
                if len(covered) else np.nan
            )
            summary[f"avg_width_bps_{label}"] = (
                float(widths.mean()) if len(widths) else np.nan
            )
            summary[f"interval_eval_records_{label}"] = int(len(covered))

        summaries.append(summary)

    return {
        "evaluation_rows": evaluation_rows,
        "summaries": summaries,
        "coverage_levels": levels,
        "calibration_window": calibration_window,
        "min_probability_history": int(min_probability_history),
        "min_interval_history": int(min_interval_history),
        "notes": [
            "Each fold is calibrated only by OOS predictions from earlier folds.",
            "The current fold is appended to calibration history only after its probabilities and intervals are evaluated.",
            "Rolling residual intervals are conformal-style diagnostics under nonstationary market data; empirical coverage is reported rather than guaranteed.",
        ],
    }


def _current_point_forecasts(
    feature_frame: pd.DataFrame,
    *,
    ticker: str,
    model: str,
    horizons: Iterable[int],
    random_state: int,
    sequence_lookback: int,
    deep_epochs: int,
) -> list[dict]:
    features = research_feature_columns(feature_frame)
    latest_idx = len(feature_frame) - 1
    latest_date = pd.Timestamp(feature_frame.iloc[latest_idx]["Date"])
    latest_price = float(feature_frame.iloc[latest_idx]["Close"])
    X_all = feature_frame[features].replace([np.inf, -np.inf], np.nan)
    out = []

    for horizon in sorted({int(h) for h in horizons if int(h) > 0}):
        cols = target_columns(horizon)
        y = pd.to_numeric(feature_frame[cols["log_return"]], errors="coerce")
        target_end = pd.to_datetime(feature_frame[cols["end_date"]], errors="coerce")
        train_mask = y.notna() & target_end.notna() & (target_end <= latest_date)
        train_indices = np.flatnonzero(train_mask.to_numpy())

        if len(train_indices) < max(120, 8 * horizon):
            continue

        train_end = int(train_indices.max()) + 1

        if is_sequence_model(model):
            pred, _ = fit_predict_sequence(
                model,
                X_all,
                y,
                train_start=0,
                train_end=train_end,
                test_start=latest_idx,
                test_end=latest_idx + 1,
                lookback=int(sequence_lookback),
                epochs=int(deep_epochs),
                random_state=int(random_state + 5000 + horizon),
            )
            if not len(pred):
                continue
            point = float(pred[0])
        else:
            fitted = build_tabular_model(model, int(random_state + 5000 + horizon))
            if fitted is None:
                raise RuntimeError(f"Could not build model: {model}")
            fitted.fit(X_all.iloc[train_indices], y.iloc[train_indices])
            point = float(
                np.asarray(
                    fitted.predict(X_all.iloc[[latest_idx]]),
                    dtype=float,
                )[0]
            )

        out.append({
            "horizon": int(horizon),
            "origin_date": latest_date.isoformat(),
            "target_date": _future_target_date(latest_date, horizon, ticker),
            "current_price": latest_price,
            "predicted_return": point,
            "predicted_return_pct": float((np.exp(point) - 1.0) * 100.0),
            "predicted_price": float(latest_price * np.exp(point)),
            "train_observations": int(len(train_indices)),
        })

    return out


def calibrate_current_forecasts(
    point_forecasts: list[dict],
    oos_records: list[dict],
    *,
    coverage_levels: Iterable[float] = DEFAULT_COVERAGE_LEVELS,
    calibration_window: int | None = 120,
    min_probability_history: int = 40,
    min_interval_history: int = 40,
) -> list[dict]:
    levels = _clean_levels(coverage_levels)
    oos = pd.DataFrame(oos_records)
    results = []

    for point in point_forecasts:
        horizon = int(point["horizon"])
        hist = (
            oos[oos["horizon"] == horizon].copy()
            if not oos.empty else pd.DataFrame()
        )
        if not hist.empty:
            hist["origin_date"] = pd.to_datetime(hist["origin_date"], errors="coerce")
            hist = _history_window(hist, calibration_window)

        row = dict(point)
        samples = int(len(hist))
        if samples >= 60:
            status = "CALIBRATED"
        elif samples >= 30:
            status = "LOW_SAMPLE"
        else:
            status = "PROVISIONAL"

        row["calibration_status"] = status
        row["calibration_samples"] = samples

        if samples >= int(min_probability_history):
            prob_model, fallback = _fit_probability_model(hist)
            prob = _predict_probability(
                prob_model,
                fallback,
                np.asarray([float(point["predicted_return"])], dtype=float),
            )[0]
            row["prob_up_pct"] = float(prob * 100.0)
        else:
            row["prob_up_pct"] = np.nan

        residuals = (
            np.abs(
                hist["actual_return"].to_numpy(dtype=float)
                - hist["predicted_return"].to_numpy(dtype=float)
            )
            if samples else np.asarray([], dtype=float)
        )

        for level in levels:
            label = int(round(level * 100))
            q = (
                _finite_sample_quantile(residuals, level)
                if samples >= int(min_interval_history)
                else np.nan
            )
            pred = float(point["predicted_return"])
            low_ret = pred - q if np.isfinite(q) else np.nan
            high_ret = pred + q if np.isfinite(q) else np.nan
            price = float(point["current_price"])

            row[f"lower_return_pct_{label}"] = (
                float((np.exp(low_ret) - 1.0) * 100.0)
                if np.isfinite(low_ret) else np.nan
            )
            row[f"upper_return_pct_{label}"] = (
                float((np.exp(high_ret) - 1.0) * 100.0)
                if np.isfinite(high_ret) else np.nan
            )
            row[f"lower_price_{label}"] = (
                float(price * np.exp(low_ret))
                if np.isfinite(low_ret) else np.nan
            )
            row[f"upper_price_{label}"] = (
                float(price * np.exp(high_ret))
                if np.isfinite(high_ret) else np.nan
            )
            row[f"conformal_radius_bps_{label}"] = (
                float(q * 10000.0) if np.isfinite(q) else np.nan
            )

        results.append(row)

    return results


def run_uncertainty_research(
    feature_frame: pd.DataFrame,
    *,
    ticker: str,
    model: str = "xgboost",
    horizons: Iterable[int] = DEFAULT_RESEARCH_HORIZONS,
    n_splits: int = 6,
    test_size: int = 20,
    min_train_size: int = 180,
    embargo: int = 0,
    random_state: int = 42,
    sequence_lookback: int = 20,
    deep_epochs: int = 15,
    coverage_levels: Iterable[float] = DEFAULT_COVERAGE_LEVELS,
    calibration_window: int | None = 120,
    min_probability_history: int = 40,
    min_interval_history: int = 40,
) -> dict:
    oos = collect_oos_predictions(
        feature_frame,
        model=model,
        horizons=horizons,
        n_splits=n_splits,
        test_size=test_size,
        min_train_size=min_train_size,
        embargo=embargo,
        random_state=random_state,
        sequence_lookback=sequence_lookback,
        deep_epochs=deep_epochs,
    )

    diagnostics = prequential_calibration(
        oos["records"],
        coverage_levels=coverage_levels,
        calibration_window=calibration_window,
        min_probability_history=min_probability_history,
        min_interval_history=min_interval_history,
    )

    points = _current_point_forecasts(
        feature_frame,
        ticker=ticker,
        model=str(model).strip().lower(),
        horizons=horizons,
        random_state=random_state,
        sequence_lookback=sequence_lookback,
        deep_epochs=deep_epochs,
    )

    current = calibrate_current_forecasts(
        points,
        oos["records"],
        coverage_levels=coverage_levels,
        calibration_window=calibration_window,
        min_probability_history=min_probability_history,
        min_interval_history=min_interval_history,
    )

    return {
        "protocol_version": "3.9-calibration-uncertainty-v1",
        "ticker": str(ticker or "").upper().strip(),
        "model": str(model).strip().lower(),
        "feature_count": oos["feature_count"],
        "feature_schema_version": oos["feature_schema_version"],
        "horizons": sorted({int(h) for h in horizons if int(h) > 0}),
        "coverage_levels": diagnostics["coverage_levels"],
        "calibration_window": calibration_window,
        "current_forecasts": current,
        "calibration_summaries": diagnostics["summaries"],
        "calibration_evaluation": diagnostics["evaluation_rows"],
        "oos_records": oos["records"],
        "model_errors": oos["model_errors"],
        "notes": [
            "Point forecasts use the same causal feature schema and horizon-purged expanding-window design as the 3.7 tournament.",
            "P(up) is a post-hoc probability mapping learned only from prior out-of-sample predictions.",
            "80%/90% ranges are rolling conformal-style bands based on prior OOS absolute residuals.",
            "Market nonstationarity can break ideal conformal assumptions, so empirical coverage is always displayed.",
            "3.9 is research-only and does not alter champion, deployment, ranking, portfolio, or trading state.",
        ],
    }
