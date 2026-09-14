"""Authenticated production consensus endpoint."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.ensemble import run_ensemble_forecast
from market_forecaster.core.production_consensus import build_production_consensus
from market_forecaster.core.xgb_multihorizon import XGBOOST_AVAILABLE, run_xgb_multihorizon

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/consensus/{ticker}")
async def get_production_consensus(
    ticker: str,
    period: str = Query("2y"),
    interval: str = Query("1d"),
    horizon: int = Query(20, ge=5, le=180),
    xgb_folds: int = Query(4, ge=2, le=6),
    xgb_test_size: int = Query(24, ge=12, le=40),
):
    """Return validated classic ensemble plus gated XGBoost consensus anchors."""
    symbol = ticker.upper().strip()
    if not XGBOOST_AVAILABLE:
        raise HTTPException(503, "XGBoost runtime is not available")

    try:
        stock_df = fetch_stock_data(symbol, period, interval)
        if stock_df.empty:
            raise HTTPException(404, f"No data for {symbol}")

        ensemble = run_ensemble_forecast(symbol, stock_df, horizon)
        if not ensemble:
            raise HTTPException(422, "Classic ensemble could not produce a forecast")

        xgb = run_xgb_multihorizon(
            stock_df,
            symbol,
            interval=interval,
            n_folds=xgb_folds,
            test_size=xgb_test_size,
        )
        consensus = build_production_consensus(ensemble, xgb, symbol)
        payload = consensus.to_dict()
        payload["xgb"] = xgb.to_dict()
        payload["ensemble_metadata"] = {
            "weights": ensemble.get("weights", {}),
            "routing_prior": ensemble.get("routing_prior", {}),
            "weight_source": ensemble.get("weight_source"),
            "validation_errors_smape": ensemble.get("validation_errors_smape", {}),
            "interval_method": ensemble.get("interval_method"),
        }
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("production_consensus_failed ticker=%s", symbol)
        raise HTTPException(500, "Production consensus calculation failed") from exc
