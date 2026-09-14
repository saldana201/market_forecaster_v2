"""
Market Forecaster — AutoTune API Route
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from market_forecaster.config import ForecastRequest
from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.indicators import add_technical_indicators
from market_forecaster.core.patterns import detect_chart_patterns, append_pattern_features
from market_forecaster.core.prophet_model import prepare_for_prophet, evaluate_oos
from market_forecaster.autotune.config_store import ConfigStore

import numpy as np

logger = logging.getLogger(__name__)
router = APIRouter()


class AutoTuneRequest(BaseModel):
    ticker: str
    period: str = "1y"
    interval: str = "1d"
    horizon: int = Field(30, ge=7, le=180)
    holdout_days: int = Field(15, ge=5, le=60)
    budget: int = Field(24, description="Number of trials: 12=quick, 24=balanced, 48=deep")


class AutoTuneResponse(BaseModel):
    ticker: str
    best_params: dict = {}
    best_metrics: dict = {}
    trials_run: int = 0
    timestamp: str = ""


@router.post("/autotune", response_model=AutoTuneResponse)
async def run_autotune(req: AutoTuneRequest):
    """Run AutoTune to find optimal Prophet configuration."""
    try:
        stock_df = fetch_stock_data(req.ticker.upper(), req.period, req.interval)
        if stock_df.empty:
            raise HTTPException(404, f"No data for {req.ticker}")

        stock_df = add_technical_indicators(stock_df)
        try:
            patterns = detect_chart_patterns(stock_df)
            stock_df = append_pattern_features(stock_df, patterns)
        except Exception:
            pass

        prophet_df = prepare_for_prophet(stock_df)

        folds = 1
        if req.budget >= 24:
            folds = 2
        if req.budget >= 48:
            folds = 3

        # Grid
        cps_pool = [0.02, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25]
        sps_pool = [2.0, 4.0, 6.0, 8.0, 10.0, 12.0]
        seas_pool = ["multiplicative", "additive"]

        candidates = []
        for seas in seas_pool:
            for cps in cps_pool:
                for sps in sps_pool:
                    candidates.append({"cps": cps, "sps": sps, "seasonality_mode": seas})

        # Limit
        if len(candidates) > req.budget * 3:
            np.random.seed(42)
            indices = np.random.choice(len(candidates), size=req.budget * 3, replace=False)
            candidates = [candidates[i] for i in sorted(indices)]

        best_stability = float("inf")
        best_params = {}
        best_metrics = {}

        for cand in candidates:
            model_kwargs = {
                "growth": "linear",
                "changepoint_prior_scale": cand["cps"],
                "seasonality_prior_scale": cand["sps"],
                "seasonality_mode": cand["seasonality_mode"],
            }

            metrics = evaluate_oos(
                prophet_df, req.holdout_days, model_kwargs,
                growth_mode="linear", n_folds=folds,
            )

            stability = metrics.get("stability_score", float("inf"))
            if not np.isnan(stability) and stability < best_stability:
                best_stability = stability
                best_params = {
                    "growth_mode": "linear",
                    "seasonality_mode": cand["seasonality_mode"],
                    "cps": cand["cps"],
                    "sps": cand["sps"],
                }
                best_metrics = {
                    "mape_mean": metrics.get("mape_mean"),
                    "mape_std": metrics.get("mape_std"),
                    "stability_score": stability,
                    "dir_accuracy": metrics.get("directional_accuracy_mean"),
                    "folds": metrics.get("n_folds"),
                }

        # Persist
        if best_params:
            store = ConfigStore()
            store.save(req.ticker.upper(), best_params, best_metrics)

        return AutoTuneResponse(
            ticker=req.ticker.upper(),
            best_params=best_params,
            best_metrics=best_metrics,
            trials_run=len(candidates),
            timestamp=datetime.utcnow().isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AutoTune failed: {e}", exc_info=True)
        raise HTTPException(500, str(e))


@router.get("/autotune/{ticker}")
async def get_best_config(ticker: str):
    """Retrieve best-known config for a ticker."""
    store = ConfigStore()
    result = store.get(ticker.upper())
    if not result:
        raise HTTPException(404, f"No saved config for {ticker}")
    return {"ticker": ticker.upper(), **result}
