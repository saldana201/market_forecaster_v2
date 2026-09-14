"""
Market Forecaster — AutoTune Engine
Two-stage grid search with stability penalty and best-config persistence.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st

from market_forecaster.config import ForecastRequest
from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.indicators import add_technical_indicators
from market_forecaster.core.patterns import detect_chart_patterns, append_pattern_features
from market_forecaster.core.prophet_model import prepare_for_prophet, evaluate_oos
from market_forecaster.autotune.config_store import ConfigStore

logger = logging.getLogger(__name__)


def _budget_to_int(budget_label: str) -> int:
    mapping = {"Quick (12)": 12, "Balanced (24)": 24, "Deep (48)": 48}
    return mapping.get(budget_label, 24)


def _folds_for_budget(budget: int) -> int:
    if budget >= 48:
        return 3
    if budget >= 24:
        return 2
    return 1


def run_autotune(req: ForecastRequest, budget_label: str = "Balanced (24)") -> dict:
    """
    Run AutoTune for a ticker. Two-stage: coarse scan → local refinement.

    Scoring: stability_score = mean_mape + 0.25 * std_mape
    Lower is better.

    Returns dict with: best_params, leaderboard (DataFrame), metrics.
    """
    budget = _budget_to_int(budget_label)
    folds = _folds_for_budget(budget)

    # Fetch and prepare data
    with st.spinner(f"Fetching data for {req.ticker}..."):
        stock_df = fetch_stock_data(req.ticker, req.period, req.interval)
        if stock_df.empty:
            return {"error": f"No data for {req.ticker}"}
        stock_df = add_technical_indicators(stock_df)
        try:
            patterns = detect_chart_patterns(stock_df)
            stock_df = append_pattern_features(stock_df, patterns)
        except Exception:
            pass
        prophet_df = prepare_for_prophet(stock_df)

    if prophet_df is None or prophet_df.empty:
        return {"error": "Could not prepare data"}

    # Stage 1: Coarse grid
    cps_pool = sorted(set([0.02, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25]))
    sps_pool = sorted(set([2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 15.0]))
    growth_pool = ["linear"]
    seas_pool = ["multiplicative", "additive"]

    candidates = []
    for growth in growth_pool:
        for seas in seas_pool:
            for cps in cps_pool:
                for sps in sps_pool:
                    candidates.append({
                        "growth": growth, "seasonality_mode": seas,
                        "cps": cps, "sps": sps,
                    })

    # Limit to budget
    if len(candidates) > budget * 3:
        np.random.seed(42)
        indices = np.random.choice(len(candidates), size=budget * 3, replace=False)
        candidates = [candidates[i] for i in sorted(indices)]

    # Always include current settings
    candidates.insert(0, {
        "growth": req.growth_mode, "seasonality_mode": req.seasonality_mode,
        "cps": req.cps, "sps": req.sps,
    })

    # Evaluate
    results = []
    progress = st.progress(0, text="Stage 1: Coarse search...")
    best_stability = float("inf")

    for i, cand in enumerate(candidates):
        progress.progress((i + 1) / len(candidates), text=f"Stage 1: Trial {i+1}/{len(candidates)}")

        model_kwargs = {
            "growth": cand["growth"],
            "changepoint_prior_scale": cand["cps"],
            "seasonality_prior_scale": cand["sps"],
            "seasonality_mode": cand["seasonality_mode"],
        }

        metrics = evaluate_oos(
            prophet_df, req.holdout_days, model_kwargs,
            use_options=req.use_options,
            growth_mode=cand["growth"],
            n_folds=folds,
        )

        stability = metrics.get("stability_score", float("inf"))
        if np.isnan(stability):
            stability = float("inf")

        results.append({
            **cand,
            "mape_mean": metrics.get("mape_mean", np.nan),
            "mape_std": metrics.get("mape_std", 0),
            "mae_mean": metrics.get("mae_mean", np.nan),
            "rmse_mean": metrics.get("rmse_mean", np.nan),
            "smape_mean": metrics.get("smape_mean", np.nan),
            "dir_accuracy": metrics.get("directional_accuracy_mean", np.nan),
            "stability_score": stability,
            "folds": metrics.get("n_folds", 0),
            "stage": "coarse",
        })

        if stability < best_stability:
            best_stability = stability

    progress.empty()

    # Stage 2: Refine around top 3 (diverse)
    leaderboard = pd.DataFrame(results).sort_values("stability_score").reset_index(drop=True)
    valid = leaderboard[leaderboard["stability_score"] < float("inf")]

    if len(valid) >= 3:
        top3 = _diverse_top_n(valid, n=3)

        refine_candidates = []
        for _, row in top3.iterrows():
            base_cps = row["cps"]
            base_sps = row["sps"]
            for cps_delta in [-0.02, -0.01, 0.01, 0.02]:
                for sps_delta in [-1.0, -0.5, 0.5, 1.0]:
                    refine_candidates.append({
                        "growth": row["growth"],
                        "seasonality_mode": row["seasonality_mode"],
                        "cps": round(max(0.01, min(0.50, base_cps + cps_delta)), 4),
                        "sps": round(max(0.1, min(20.0, base_sps + sps_delta)), 2),
                    })

        # Deduplicate
        seen = set()
        unique = []
        for c in refine_candidates:
            key = (c["growth"], c["seasonality_mode"], c["cps"], c["sps"])
            if key not in seen:
                seen.add(key)
                unique.append(c)
        refine_candidates = unique

        progress2 = st.progress(0, text="Stage 2: Refining top candidates...")

        for i, cand in enumerate(refine_candidates):
            progress2.progress((i + 1) / len(refine_candidates), text=f"Stage 2: {i+1}/{len(refine_candidates)}")

            model_kwargs = {
                "growth": cand["growth"],
                "changepoint_prior_scale": cand["cps"],
                "seasonality_prior_scale": cand["sps"],
                "seasonality_mode": cand["seasonality_mode"],
            }

            metrics = evaluate_oos(
                prophet_df, req.holdout_days, model_kwargs,
                use_options=req.use_options,
                growth_mode=cand["growth"],
                n_folds=folds,
            )

            stability = metrics.get("stability_score", float("inf"))
            if np.isnan(stability):
                stability = float("inf")

            results.append({
                **cand,
                "mape_mean": metrics.get("mape_mean", np.nan),
                "mape_std": metrics.get("mape_std", 0),
                "mae_mean": metrics.get("mae_mean", np.nan),
                "rmse_mean": metrics.get("rmse_mean", np.nan),
                "smape_mean": metrics.get("smape_mean", np.nan),
                "dir_accuracy": metrics.get("directional_accuracy_mean", np.nan),
                "stability_score": stability,
                "folds": metrics.get("n_folds", 0),
                "stage": "refine",
            })

        progress2.empty()

    # Final leaderboard
    leaderboard = pd.DataFrame(results).sort_values("stability_score").reset_index(drop=True)
    best_row = leaderboard.iloc[0] if not leaderboard.empty else None

    if best_row is not None and best_row["stability_score"] < float("inf"):
        best_params = {
            "growth_mode": best_row["growth"],
            "seasonality_mode": best_row["seasonality_mode"],
            "cps": float(best_row["cps"]),
            "sps": float(best_row["sps"]),
        }
        best_metrics = {
            "mape_mean": float(best_row["mape_mean"]),
            "mape_std": float(best_row["mape_std"]),
            "stability_score": float(best_row["stability_score"]),
            "dir_accuracy": float(best_row.get("dir_accuracy", 0)),
            "folds": int(best_row["folds"]),
        }

        # Persist
        store = ConfigStore()
        store.save(req.ticker, best_params, best_metrics)

        return {
            "best_params": best_params,
            "best_metrics": best_metrics,
            "leaderboard": leaderboard,
        }

    return {"error": "AutoTune found no valid configurations", "leaderboard": leaderboard}


def _diverse_top_n(df: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    """Select top-N diverse candidates to avoid refining near-duplicates."""
    if len(df) <= n:
        return df

    selected = [df.iloc[0]]
    for _, row in df.iloc[1:].iterrows():
        if len(selected) >= n:
            break
        # Check diversity: different seasonality OR CPS bucket differs by > 0.05
        is_diverse = any([
            row["seasonality_mode"] != selected[-1]["seasonality_mode"],
            abs(row["cps"] - selected[-1]["cps"]) > 0.05,
            abs(row["sps"] - selected[-1]["sps"]) > 3.0,
        ])
        if is_diverse:
            selected.append(row)

    # Fill remaining from top if not enough diverse
    if len(selected) < n:
        for _, row in df.iterrows():
            if len(selected) >= n:
                break
            key = (row["growth"], row["seasonality_mode"], row["cps"], row["sps"])
            existing = {(s["growth"], s["seasonality_mode"], s["cps"], s["sps"]) for s in selected}
            if key not in existing:
                selected.append(row)

    return pd.DataFrame(selected)
