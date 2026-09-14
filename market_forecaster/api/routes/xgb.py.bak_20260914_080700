"""Authenticated XGBoost multi-horizon forecast endpoint."""
from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, Query

from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.xgb_multihorizon import run_xgb_multihorizon

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/xgb/{ticker}")
async def xgb_multihorizon(
    ticker: str,
    period: str = Query("5y"),
    interval: str = Query("1d"),
    folds: int = Query(4, ge=2, le=6),
    test_size: int = Query(24, ge=12, le=40),
):
    try:
        stock_df = fetch_stock_data(ticker, period, interval)
        if stock_df.empty:
            raise HTTPException(404, f"No data for {ticker}")
        result = run_xgb_multihorizon(
            stock_df, ticker,
            interval=interval,
            n_folds=folds,
            test_size=test_size,
        )
        return result.to_dict()
    except HTTPException:
        raise
    except RuntimeError as exc:
        logger.warning("xgb_unavailable ticker=%s error=%s", ticker, exc)
        raise HTTPException(503, "XGBoost forecast engine is unavailable")
    except Exception as exc:
        logger.error("xgb_forecast_failed ticker=%s error=%s", ticker, exc, exc_info=True)
        raise HTTPException(500, "XGBoost forecast failed")
