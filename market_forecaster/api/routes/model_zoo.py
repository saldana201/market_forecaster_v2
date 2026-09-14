"""Production Model Zoo API route."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.model_zoo import run_model_zoo

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/model-zoo/{ticker}")
async def model_zoo(
    ticker: str,
    period: str = Query("2y"),
    interval: str = Query("1d"),
    test_size: int = Query(20, ge=5, le=60),
    folds: int = Query(5, ge=2, le=10),
    gap: int = Query(1, ge=0, le=10),
):
    """Compare production baseline models on identical chronological folds."""
    try:
        stock_df = fetch_stock_data(ticker, period, interval)
        if stock_df.empty:
            raise HTTPException(404, f"No data for {ticker.upper()}")
        result = run_model_zoo(stock_df, test_size=test_size, n_folds=folds, gap=gap)
        return {
            "ticker": ticker.upper(),
            "winner": result.winner,
            "naive_smape": result.naive_smape,
            "config": result.config,
            "leaderboard": result.leaderboard.to_dict(orient="records"),
            "folds": result.folds.to_dict(orient="records"),
            "notes": result.notes,
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        logger.exception("model_zoo_failed ticker=%s", ticker)
        raise HTTPException(500, "Model Zoo failed")
