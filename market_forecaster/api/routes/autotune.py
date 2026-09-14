"""AutoTune API route using the same OOS protocol as production forecasts."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from market_forecaster.autotune.config_store import ConfigStore
from market_forecaster.core.data import fetch_stock_data, infer_forecast_freq
from market_forecaster.core.indicators import add_technical_indicators
from market_forecaster.core.prophet_model import evaluate_oos, prepare_for_prophet

logger = logging.getLogger(__name__)
router = APIRouter()


class AutoTuneRequest(BaseModel):
    ticker: str
    period: str = "1y"
    interval: str = "1d"
    horizon: int = Field(30, ge=7, le=180)
    holdout_days: int = Field(15, ge=5, le=60)
    budget: int = Field(24, ge=6, le=48)


class AutoTuneResponse(BaseModel):
    ticker: str
    best_params: dict = Field(default_factory=dict)
    best_metrics: dict = Field(default_factory=dict)
    trials_run: int = 0
    timestamp: str = ""


@router.post("/autotune", response_model=AutoTuneResponse)
async def run_autotune(req: AutoTuneRequest):
    symbol = req.ticker.upper().strip()
    try:
        stock_df = fetch_stock_data(symbol, req.period, req.interval)
        if stock_df.empty:
            raise HTTPException(404, f"No data for {symbol}")
        prophet_df = prepare_for_prophet(add_technical_indicators(stock_df))
        folds = 1 if req.budget < 24 else 2 if req.budget < 48 else 3
        freq = infer_forecast_freq(symbol, req.interval)

        candidates = [
            {"cps": cps, "sps": sps, "seasonality_mode": seas}
            for seas in ("multiplicative", "additive")
            for cps in (0.02, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25)
            for sps in (2.0, 4.0, 6.0, 8.0, 10.0, 12.0)
        ]
        rng = np.random.default_rng(42)
        if len(candidates) > req.budget:
            idx = np.sort(rng.choice(len(candidates), size=req.budget, replace=False))
            candidates = [candidates[i] for i in idx]

        best_stability = float("inf")
        best_params: dict = {}
        best_metrics: dict = {}
        for cand in candidates:
            kwargs = {
                "growth": "linear",
                "changepoint_prior_scale": cand["cps"],
                "seasonality_prior_scale": cand["sps"],
                "seasonality_mode": cand["seasonality_mode"],
            }
            metrics = evaluate_oos(
                prophet_df,
                req.holdout_days,
                kwargs,
                growth_mode="linear",
                n_folds=folds,
                future_freq=freq,
            )
            stability = float(metrics.get("stability_score", float("inf")))
            if np.isfinite(stability) and stability < best_stability:
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

        if best_params:
            ConfigStore().save(symbol, best_params, best_metrics)
        return AutoTuneResponse(
            ticker=symbol,
            best_params=best_params,
            best_metrics=best_metrics,
            trials_run=len(candidates),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("autotune_failed ticker=%s", symbol)
        raise HTTPException(500, "AutoTune execution failed")


@router.get("/autotune/{ticker}")
async def get_best_config(ticker: str):
    symbol = ticker.upper().strip()
    result = ConfigStore().get(symbol)
    if not result:
        raise HTTPException(404, f"No saved config for {symbol}")
    return {"ticker": symbol, **result}
