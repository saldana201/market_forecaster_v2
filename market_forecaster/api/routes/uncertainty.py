"""Probability calibration / uncertainty research API for Market Forecaster 3.9."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.feature_store import build_feature_store
from market_forecaster.core.market_context import build_market_context
from market_forecaster.core.uncertainty_calibration import run_uncertainty_research

router = APIRouter()


@router.get("/research/uncertainty/{ticker}")
async def uncertainty_research(
    ticker: str,
    period: str = Query("10y"),
    model: str = Query("xgboost"),
    context_family: str | None = Query(None),
    sector_ticker: str | None = Query(None),
    n_splits: int = Query(6, ge=4, le=8),
    test_size: int = Query(20, ge=15, le=40),
    calibration_window: int = Query(120, ge=0, le=500),
):
    symbol = ticker.upper().strip()
    market = fetch_stock_data(symbol, period, "1d")
    if market.empty:
        raise HTTPException(status_code=404, detail="No market data available")

    frame, metadata = build_feature_store(market, symbol)
    context_used = "none"

    if context_family and context_family.lower() != "none":
        family = context_family.lower().strip()
        enriched, registry = build_market_context(
            frame,
            symbol,
            period=period,
            families=[family],
            sector_ticker=sector_ticker,
        )
        if registry.get(family, {}).get("available"):
            frame = enriched
            context_used = family

    result = run_uncertainty_research(
        frame,
        ticker=symbol,
        model=model,
        n_splits=n_splits,
        test_size=test_size,
        calibration_window=None if calibration_window == 0 else calibration_window,
    )
    result["dataset_metadata"] = metadata.to_dict()
    result["context_family"] = context_used
    return result
