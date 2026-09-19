"""Feature-family ablation engine for Market Forecaster 3.8."""
from __future__ import annotations
from typing import Iterable
import numpy as np
import pandas as pd

from market_forecaster.core.experiment_runner import run_research_experiment
from market_forecaster.core.feature_store import research_feature_columns
from market_forecaster.core.targets import DEFAULT_RESEARCH_HORIZONS
from market_forecaster.core.validation import paired_fold_improvement
from market_forecaster.core.model_tournament import BASELINE_MODELS

DEFAULT_ABLATION_MODELS = ("ridge", "hist_gradient_boosting", "xgboost")

def _feature_view(frame: pd.DataFrame, selected_features: Iterable[str]) -> pd.DataFrame:
    selected = []
    for feature in selected_features:
        feature = str(feature)
        if feature in frame.columns and feature not in selected:
            selected.append(feature)
    metadata = [
        c for c in ("Date", "Close", "ticker", "feature_asof", "feature_schema_version")
        if c in frame.columns
    ]
    targets = [c for c in frame.columns if c.startswith("target_")]
    out = frame[[*metadata, *selected, *targets]].copy()
    out.attrs.update(getattr(frame, "attrs", {}))
    return out

def _fold_signature(result: dict) -> set[tuple]:
    return {
        (
            int(row["horizon"]),
            int(row["fold"]),
            str(row["model"]),
            str(row["train_last_date"]),
            str(row["test_first_date"]),
        )
        for row in result.get("folds", [])
    }

def _comparison_rows(family: str, baseline: dict, enhanced: dict, *, random_state: int) -> list[dict]:
    base = pd.DataFrame(baseline.get("folds", []))
    test = pd.DataFrame(enhanced.get("folds", []))
    if base.empty or test.empty:
        return []
    keys = ["horizon", "fold", "model", "train_last_date", "test_first_date"]
    merged = base.merge(test, on=keys, how="inner", suffixes=("_base", "_plus"))
    if merged.empty:
        return []

    summaries_base = pd.DataFrame(baseline.get("summaries", []))
    summaries_plus = pd.DataFrame(enhanced.get("summaries", []))
    rows = []

    for (horizon, model), group in merged.groupby(["horizon", "model"], sort=True):
        if str(model) in BASELINE_MODELS:
            continue
        b = group["return_mae_bps_base"].to_numpy(dtype=float)
        p = group["return_mae_bps_plus"].to_numpy(dtype=float)
        valid = np.isfinite(b) & np.isfinite(p) & (b > 0)
        b, p = b[valid], p[valid]
        if not len(b):
            continue

        baseline_mae = float(np.mean(b))
        plus_mae = float(np.mean(p))
        lift = (baseline_mae - plus_mae) / baseline_mae * 100.0
        win_rate = float(np.mean(p < b) * 100.0)
        evidence = paired_fold_improvement(
            p,
            b,
            seed=int(random_state + int(horizon) + sum(ord(ch) for ch in family)),
        )

        bsum = summaries_base[
            (summaries_base["horizon"] == horizon)
            & (summaries_base["model"] == model)
        ]
        psum = summaries_plus[
            (summaries_plus["horizon"] == horizon)
            & (summaries_plus["model"] == model)
        ]
        base_dir = float(bsum["directional_accuracy_pct"].iloc[0]) if not bsum.empty else np.nan
        plus_dir = float(psum["directional_accuracy_pct"].iloc[0]) if not psum.empty else np.nan
        direction_delta = plus_dir - base_dir if np.isfinite(base_dir) and np.isfinite(plus_dir) else np.nan

        observations = int(group["test_rows_plus"].sum())
        folds = int(group["fold"].nunique())
        ci_low = evidence["ci_low_pct"]
        ci_high = evidence["ci_high_pct"]

        if (
            folds >= 3
            and observations >= 60
            and lift >= 2.0
            and np.isfinite(ci_low)
            and ci_low > 0.0
            and (not np.isfinite(direction_delta) or direction_delta >= -1.0)
        ):
            status = "SUPPORTED"
        elif lift > 0:
            status = "MIXED"
        else:
            status = "NO_LIFT"

        rows.append({
            "family": family,
            "horizon": int(horizon),
            "model": str(model),
            "folds": folds,
            "observations": observations,
            "baseline_mae_bps": baseline_mae,
            "family_mae_bps": plus_mae,
            "mae_lift_pct": float(lift),
            "fold_win_rate_pct": win_rate,
            "lift_ci_low_pct": float(ci_low),
            "lift_ci_high_pct": float(ci_high),
            "baseline_direction_pct": base_dir,
            "family_direction_pct": plus_dir,
            "direction_delta_pct_points": direction_delta,
            "evidence_status": status,
        })
    return rows

def run_feature_ablation(
    base_feature_frame: pd.DataFrame,
    enriched_frame: pd.DataFrame,
    family_registry: dict,
    *,
    families: Iterable[str] | None = None,
    models: Iterable[str] = DEFAULT_ABLATION_MODELS,
    horizons: Iterable[int] = DEFAULT_RESEARCH_HORIZONS,
    n_splits: int = 5,
    test_size: int = 20,
    min_train_size: int = 180,
    embargo: int = 0,
    random_state: int = 42,
) -> dict:
    base_features = research_feature_columns(base_feature_frame)
    if not base_features:
        raise ValueError("Base research feature set is empty")

    requested = list(families) if families is not None else list(family_registry)
    requested = [str(x).strip().lower() for x in requested]

    common_kwargs = dict(
        horizons=horizons,
        models=models,
        n_splits=n_splits,
        test_size=test_size,
        min_train_size=min_train_size,
        embargo=embargo,
        random_state=random_state,
    )
    baseline_view = _feature_view(enriched_frame, base_features)
    baseline = run_research_experiment(baseline_view, **common_kwargs)
    baseline_signature = _fold_signature(baseline)

    comparisons = []
    family_summaries = []
    runs = {"baseline": baseline}

    for family in requested:
        info = family_registry.get(family, {})
        columns = [
            c for c in info.get("columns", [])
            if c in enriched_frame.columns
            and pd.api.types.is_numeric_dtype(enriched_frame[c])
        ]
        if not info.get("available") or not columns:
            family_summaries.append({
                "family": family,
                "status": "UNAVAILABLE",
                "feature_count": len(columns),
                "coverage_pct": float(info.get("coverage_pct", 0.0) or 0.0),
                "supported_tests": 0,
                "mixed_tests": 0,
                "no_lift_tests": 0,
                "mean_mae_lift_pct": np.nan,
            })
            continue

        view = _feature_view(enriched_frame, [*base_features, *columns])
        run = run_research_experiment(view, **common_kwargs)
        runs[family] = run

        if _fold_signature(run) != baseline_signature:
            family_summaries.append({
                "family": family,
                "status": "PROTOCOL_MISMATCH",
                "feature_count": len(columns),
                "coverage_pct": float(info.get("coverage_pct", 0.0) or 0.0),
                "supported_tests": 0,
                "mixed_tests": 0,
                "no_lift_tests": 0,
                "mean_mae_lift_pct": np.nan,
            })
            continue

        rows = _comparison_rows(family, baseline, run, random_state=random_state)
        comparisons.extend(rows)
        statuses = [row["evidence_status"] for row in rows]
        lifts = [row["mae_lift_pct"] for row in rows if np.isfinite(row["mae_lift_pct"])]

        if any(s == "SUPPORTED" for s in statuses):
            family_status = "EVIDENCE_FOUND"
        elif any(s == "MIXED" for s in statuses):
            family_status = "MIXED"
        else:
            family_status = "NO_LIFT"

        family_summaries.append({
            "family": family,
            "status": family_status,
            "feature_count": len(columns),
            "coverage_pct": float(info.get("coverage_pct", 0.0) or 0.0),
            "supported_tests": statuses.count("SUPPORTED"),
            "mixed_tests": statuses.count("MIXED"),
            "no_lift_tests": statuses.count("NO_LIFT"),
            "mean_mae_lift_pct": float(np.mean(lifts)) if lifts else np.nan,
        })

    return {
        "protocol_version": "3.8-feature-ablation-v1",
        "base_feature_count": len(base_features),
        "families_requested": requested,
        "models": [str(x).strip().lower() for x in models],
        "horizons": sorted({int(h) for h in horizons if int(h) > 0}),
        "family_registry": family_registry,
        "family_summaries": family_summaries,
        "comparisons": comparisons,
        "baseline_result": baseline,
        "family_runs": runs,
        "notes": [
            "Ablations add exactly one context family to the unchanged base price/volume feature set.",
            "Baseline and enhanced runs must have identical fold/date signatures before lift is reported.",
            "SUPPORTED requires >=3 folds, >=60 OOS observations, >=2% MAE lift, paired-fold CI lower bound >0, and no material directional-accuracy deterioration.",
            "Feature-family evidence is research-only; 3.8 does not mutate production model or deployment state.",
            "Daily context uses backward-only alignment and never consumes a context observation dated after the target forecast origin.",
        ],
    }
