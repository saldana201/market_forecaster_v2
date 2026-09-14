"""Historical Options Intelligence API route."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.historical_options import evaluate_options_history
from market_forecaster.core.options_flow_v2 import load_options_history

router = APIRouter()


@router.get("/options-history/{ticker}")
async def get_options_history_validation(
    ticker: str,
    period: str = Query("2y", description="Price history used to label future returns"),
):
    symbol = ticker.upper().strip()
    history = load_options_history(symbol, limit=10000)
    if not history:
        return {
            "ticker": symbol,
            "status": "COLLECTING",
            "unique_sessions": 0,
            "reason": "No persisted real Options Flow v2 snapshots yet",
            "routing_effect": "NONE_IN_2_7",
        }
    stock_df = fetch_stock_data(symbol, period, "1d")
    if stock_df.empty:
        raise HTTPException(404, f"No market data for {symbol}")
    result = evaluate_options_history(history, stock_df)
    result["ticker"] = symbol
    return result
