"""Leakage-controlled multi-horizon Model Tournament (v3.7).

3.7 preserves the 3.6 research contract and expands only the challenger set.
Every model uses the same causal feature store, target-origin rows, chronological
folds, horizon-aware embargo, and metrics.

Sequence models consume a causal feature lookback ending at the same target
origin used by tabular models. No validation target is used during fitting.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from market_forecaster.core.feature_store import (
    assert_point_in_time_integrity,
    research_feature_columns,
)
from market_forecaster.core.model_tournament import (
    ALL_MODELS,
    BASELINE_MODELS,
    DEFAULT_FAST_MODELS,
    SEQUENCE_MODELS,
    build_tabular_model,
    fit_predict_sequence,
    is_model_available,
    is_sequence_model,
    model_status_map,
)
from market_forecaster.core.targets import DEFAULT_RESEARCH_HORIZONS, target_columns
from market_forecaster.core.validation import expanding_window_splits, paired_fold_improvement

DEFAULT_MODELS = DEFAULT_FAST_MODELS
TOURNAMENT_MODELS = ALL_MODELS


@dataclass(frozen=True)
class FoldResult:
    horizon: int
    fold: int
    model: str
    model_family: str
    train_rows: int
    test_rows: int
    train_last_date: str
    test_first_date: str
    return_mae_bps: float
    return_rmse_bps: float
    directional_accuracy_pct: float
    price_smape_pct: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ModelHorizonResult:
    horizon: int
    model: str
    model_family: str
    folds_run: int
    observations: int
    return_mae_bps: float
    return_rmse_bps: float
    directional_accuracy_pct: float
    price_smape_pct: float
    improvement_vs_zero_mae_pct: float
    fold_win_rate_vs_zero_pct: float
    improvement_ci_low_pct: float
    improvement_ci_high_pct: float
    improvement_vs_xgb_mae_pct: float
    fold_win_rate_vs_xgb_pct: float
    xgb_lift_ci_low_pct: float
    xgb_lift_ci_high_pct: float
    research_status: str
    challenger_status: str
    tournament_rank: int
    notes: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _smape(actual: np.ndarray, predicted: np.ndarray) -> float:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    denom = (np.abs(actual) + np.abs(predicted)) / 2.0
    good = np.isfinite(actual) & np.isfinite(predicted) & (denom > 0)
    if not good.any():
        return float("nan")
    return float(np.mean(np.abs(actual[good] - predicted[good]) / denom[good]) * 100.0)


def _point_metrics(y_true: np.ndarray, y_pred: np.ndarray, anchors: np.ndarray) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    anchors = np.asarray(anchors, dtype=float)
    valid = np.isfinite(y_true) & np.isfinite(y_pred) & np.isfinite(anchors) & (anchors > 0)
    y_true, y_pred, anchors = y_true[valid], y_pred[valid], anchors[valid]
    if not len(y_true):
        return {
            "mae_bps": np.nan,
            "rmse_bps": np.nan,
            "direction": np.nan,
            "price_smape": np.nan,
        }
    err = y_true - y_pred
    actual_price = anchors * np.exp(y_true)
    predicted_price = anchors * np.exp(y_pred)
    return {
        "mae_bps": float(np.mean(np.abs(err)) * 10000.0),
        "rmse_bps": float(np.sqrt(np.mean(err ** 2)) * 10000.0),
        "direction": float(np.mean(np.sign(y_true) == np.sign(y_pred)) * 100.0),
        "price_smape": _smape(actual_price, predicted_price),
    }


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
    test_start_date = pd.to_datetime(
        frame.iloc[test_start]["Date"],
        errors="coerce",
    )
    if pd.notna(train_target_end) and pd.notna(test_start_date) and train_target_end >= test_start_date:
        raise RuntimeError(
            f"Target overlap detected for {horizon}D: "
            f"last train label ends {train_target_end}, test starts {test_start_date}"
        )


def _paired_against(
    group: pd.DataFrame,
    reference: pd.DataFrame,
    *,
    seed: int,
) -> dict[str, float]:
    if group.empty or reference.empty:
        return {
            "improvement": np.nan,
            "win_rate": np.nan,
            "ci_low": np.nan,
            "ci_high": np.nan,
        }
    ref = reference[["fold", "return_mae_bps"]].rename(columns={"return_mae_bps": "ref_mae"})
    paired = group[["fold", "return_mae_bps"]].merge(ref, on="fold", how="inner")
    if paired.empty:
        return {
            "improvement": np.nan,
            "win_rate": np.nan,
            "ci_low": np.nan,
            "ci_high": np.nan,
        }
    ref_mean = float(paired["ref_mae"].mean())
    cand_mean = float(paired["return_mae_bps"].mean())
    improvement = (
        (ref_mean - cand_mean) / ref_mean * 100.0
        if np.isfinite(ref_mean) and ref_mean > 0 else np.nan
    )
    win_rate = float((paired["return_mae_bps"] < paired["ref_mae"]).mean() * 100.0)
    evidence = paired_fold_improvement(
        paired["return_mae_bps"].to_numpy(),
        paired["ref_mae"].to_numpy(),
        seed=seed,
    )
    return {
        "improvement": improvement,
        "win_rate": win_rate,
        "ci_low": evidence["ci_low_pct"],
        "ci_high": evidence["ci_high_pct"],
    }


def _research_status(
    model: str,
    folds_run: int,
    observations: int,
    direction: float,
    vs_zero: dict[str, float],
) -> tuple[str, list[str]]:
    if model == "zero_return":
        return "BASELINE", []
    notes: list[str] = []
    improvement = vs_zero["improvement"]
    ci_low = vs_zero["ci_low"]
    if (
        folds_run >= 3
        and observations >= 60
        and np.isfinite(improvement)
        and improvement >= 2.0
        and np.isfinite(direction)
        and direction >= 52.0
        and np.isfinite(ci_low)
        and ci_low > 0.0
    ):
        notes.append("Positive paired-fold improvement vs zero-return; deeper research warranted.")
        return "PROMISING", notes
    if np.isfinite(improvement) and improvement > 0:
        notes.append("Some OOS improvement vs zero-return, but evidence is not yet strong.")
        return "MIXED", notes
    notes.append("Did not improve the zero-return baseline on current OOS folds.")
    return "NO_LIFT", notes


def _challenger_status(
    model: str,
    folds_run: int,
    observations: int,
    direction: float,
    vs_xgb: dict[str, float],
    xgb_present: bool,
) -> str:
    if model in BASELINE_MODELS:
        return "BASELINE"
    if model == "xgboost":
        return "REFERENCE"
    if not xgb_present:
        return "NO_XGB_REFERENCE"
    improvement = vs_xgb["improvement"]
    ci_low = vs_xgb["ci_low"]
    if (
        folds_run >= 3
        and observations >= 60
        and np.isfinite(improvement)
        and improvement >= 2.0
        and np.isfinite(direction)
        and direction >= 52.0
        and np.isfinite(ci_low)
        and ci_low > 0.0
    ):
        return "CHALLENGER_PROMISING"
    if np.isfinite(improvement) and improvement > 0:
        return "MIXED_VS_XGB"
    return "NO_LIFT_VS_XGB"


def run_research_experiment(
    feature_frame: pd.DataFrame,
    *,
    horizons: Iterable[int] = DEFAULT_RESEARCH_HORIZONS,
    models: Iterable[str] = DEFAULT_MODELS,
    n_splits: int = 5,
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
    features = research_feature_columns(feature_frame)
    if not features:
        raise ValueError("No research features are available")

    registry = model_status_map()
    requested_models: list[str] = []
    unknown_models: list[str] = []
    unavailable: list[str] = []
    for name in models:
        name = str(name).strip().lower()
        if not name or name in requested_models:
            continue
        if name not in registry:
            unknown_models.append(name)
            continue
        requested_models.append(name)
        if not is_model_available(name):
            unavailable.append(name)

    if "zero_return" not in requested_models:
        requested_models.insert(0, "zero_return")

    fold_rows: list[dict] = []
    model_errors: list[dict] = []

    for horizon in sorted({int(h) for h in horizons if int(h) > 0}):
        cols = target_columns(horizon)
        if cols["log_return"] not in feature_frame.columns or cols["end_date"] not in feature_frame.columns:
            continue

        work = feature_frame[
            ["Date", "Close", cols["log_return"], cols["end_date"], *features]
        ].copy()
        work = work.dropna(
            subset=["Date", "Close", cols["log_return"], cols["end_date"]]
        ).reset_index(drop=True)
        if len(work) < max(min_train_size + test_size + horizon, 60):
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
            X_train = X.iloc[split.train_start:split.train_end]
            y_train = y.iloc[split.train_start:split.train_end]
            X_test = X.iloc[split.test_start:split.test_end]
            y_test = y.iloc[split.test_start:split.test_end].to_numpy(dtype=float)
            anchor_test = anchors.iloc[split.test_start:split.test_end].to_numpy(dtype=float)
            train_last_date = pd.Timestamp(work.iloc[split.train_end - 1]["Date"]).isoformat()
            test_first_date = pd.Timestamp(work.iloc[split.test_start]["Date"]).isoformat()

            for model_name in requested_models:
                spec = registry.get(model_name, {})
                if model_name in unavailable:
                    continue
                try:
                    if model_name == "zero_return":
                        pred = np.zeros(len(X_test), dtype=float)
                        actual = y_test
                        anchor_eval = anchor_test
                    elif model_name == "historical_mean":
                        mean = float(np.nanmean(y_train.to_numpy(dtype=float)))
                        pred = np.full(len(X_test), mean, dtype=float)
                        actual = y_test
                        anchor_eval = anchor_test
                    elif is_sequence_model(model_name):
                        pred, kept = fit_predict_sequence(
                            model_name,
                            X,
                            y,
                            train_start=split.train_start,
                            train_end=split.train_end,
                            test_start=split.test_start,
                            test_end=split.test_end,
                            lookback=int(sequence_lookback),
                            epochs=int(deep_epochs),
                            random_state=int(random_state + split.fold + horizon),
                        )
                        actual = y.iloc[kept].to_numpy(dtype=float)
                        anchor_eval = anchors.iloc[kept].to_numpy(dtype=float)
                    else:
                        model = build_tabular_model(
                            model_name,
                            int(random_state + split.fold + horizon),
                        )
                        if model is None:
                            if model_name not in unavailable:
                                unavailable.append(model_name)
                            continue
                        model.fit(X_train, y_train)
                        pred = np.asarray(model.predict(X_test), dtype=float)
                        actual = y_test
                        anchor_eval = anchor_test

                    metrics = _point_metrics(actual, pred, anchor_eval)
                    fold_rows.append(FoldResult(
                        horizon=horizon,
                        fold=split.fold,
                        model=model_name,
                        model_family=str(spec.get("family", "unknown")),
                        train_rows=len(X_train),
                        test_rows=len(pred),
                        train_last_date=train_last_date,
                        test_first_date=test_first_date,
                        return_mae_bps=metrics["mae_bps"],
                        return_rmse_bps=metrics["rmse_bps"],
                        directional_accuracy_pct=metrics["direction"],
                        price_smape_pct=metrics["price_smape"],
                    ).to_dict())
                except Exception as exc:
                    model_errors.append({
                        "horizon": horizon,
                        "fold": split.fold,
                        "model": model_name,
                        "error": str(exc),
                    })

    folds_df = pd.DataFrame(fold_rows)
    raw_summaries: list[dict] = []

    if not folds_df.empty:
        for (horizon, model), group in folds_df.groupby(["horizon", "model"], sort=True):
            zero = folds_df[
                (folds_df["horizon"] == horizon)
                & (folds_df["model"] == "zero_return")
            ]
            xgb = folds_df[
                (folds_df["horizon"] == horizon)
                & (folds_df["model"] == "xgboost")
            ]
            vs_zero = _paired_against(group, zero, seed=random_state + int(horizon))
            vs_xgb = _paired_against(group, xgb, seed=random_state + 1000 + int(horizon))

            direction = float(group["directional_accuracy_pct"].mean())
            folds_run = int(group["fold"].nunique())
            observations = int(group["test_rows"].sum())
            status, notes = _research_status(
                str(model), folds_run, observations, direction, vs_zero
            )
            challenger = _challenger_status(
                str(model), folds_run, observations, direction, vs_xgb, not xgb.empty
            )
            if challenger == "CHALLENGER_PROMISING":
                notes.append("Positive paired-fold evidence vs XGBoost; eligible for broader ticker testing.")

            spec = registry.get(str(model), {})
            raw_summaries.append({
                "horizon": int(horizon),
                "model": str(model),
                "model_family": str(spec.get("family", "unknown")),
                "folds_run": folds_run,
                "observations": observations,
                "return_mae_bps": float(group["return_mae_bps"].mean()),
                "return_rmse_bps": float(group["return_rmse_bps"].mean()),
                "directional_accuracy_pct": direction,
                "price_smape_pct": float(group["price_smape_pct"].mean()),
                "improvement_vs_zero_mae_pct": vs_zero["improvement"],
                "fold_win_rate_vs_zero_pct": vs_zero["win_rate"],
                "improvement_ci_low_pct": vs_zero["ci_low"],
                "improvement_ci_high_pct": vs_zero["ci_high"],
                "improvement_vs_xgb_mae_pct": vs_xgb["improvement"],
                "fold_win_rate_vs_xgb_pct": vs_xgb["win_rate"],
                "xgb_lift_ci_low_pct": vs_xgb["ci_low"],
                "xgb_lift_ci_high_pct": vs_xgb["ci_high"],
                "research_status": status,
                "challenger_status": challenger,
                "notes": notes,
            })

    summaries: list[dict] = []
    if raw_summaries:
        summary_df = pd.DataFrame(raw_summaries)
        summary_df["tournament_rank"] = 0
        for horizon, index in summary_df.groupby("horizon").groups.items():
            ranked = summary_df.loc[index].sort_values(
                ["return_mae_bps", "return_rmse_bps"], ascending=[True, True]
            )
            for rank, row_index in enumerate(ranked.index, start=1):
                summary_df.loc[row_index, "tournament_rank"] = rank
        for row in summary_df.to_dict("records"):
            summaries.append(ModelHorizonResult(**row).to_dict())

    leaders = []
    if summaries:
        summary_df = pd.DataFrame(summaries)
        for horizon in sorted(summary_df["horizon"].unique()):
            horizon_rows = summary_df[summary_df["horizon"] == horizon]
            if horizon_rows.empty:
                continue
            top = horizon_rows.sort_values("tournament_rank").iloc[0]
            leaders.append({
                "horizon": int(horizon),
                "model": str(top["model"]),
                "return_mae_bps": float(top["return_mae_bps"]),
                "directional_accuracy_pct": float(top["directional_accuracy_pct"]),
                "research_status": str(top["research_status"]),
                "challenger_status": str(top["challenger_status"]),
            })

    return {
        "protocol_version": "3.7-model-tournament-v1",
        "feature_schema_version": pit.get("schema_version"),
        "features": features,
        "feature_count": len(features),
        "horizons": sorted({int(h) for h in horizons if int(h) > 0}),
        "models_requested": requested_models,
        "models_unknown": unknown_models,
        "models_unavailable": sorted(set(unavailable)),
        "model_registry": list(registry.values()),
        "model_errors": model_errors,
        "n_splits_requested": int(n_splits),
        "test_size": int(test_size),
        "minimum_train_size": int(min_train_size),
        "embargo_rule": "max(user_embargo, horizon)",
        "sequence_lookback": int(sequence_lookback),
        "deep_epochs": int(deep_epochs),
        "summaries": summaries,
        "leaders_by_horizon": leaders,
        "folds": fold_rows,
        "notes": [
            "Research-only: results do not alter champion, deployment, consensus, ranking, portfolio state, or trading execution.",
            "Every candidate uses the same causal feature schema, target-origin dates, chronological folds, and horizon-aware embargo.",
            "Sequence models use a causal lookback ending at the same forecast origin; scalers are fitted on training rows only.",
            "Zero future return remains the mandatory baseline.",
            "XGBoost is the nonlinear challenger reference; new models are evaluated against it when available.",
            "Tournament rank is descriptive OOS MAE ordering, not a production promotion decision.",
        ],
    }
