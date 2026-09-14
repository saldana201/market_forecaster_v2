"""Adaptive Options Promotion API route."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.options_flow_v2 import load_options_history
from market_forecaster.core.options_promotion import build_options_promotion

router = APIRouter()


@router.get("/options-promotion/{ticker}")
async def get_options_promotion(
    ticker: str,
    period: str = Query("2y", description="Price history used by options validation"),
):
    symbol = ticker.upper().strip()
    history = load_options_history(symbol, limit=10000)
    if not history:
        return {
            "ticker": symbol,
            "status": "COLLECTING",
            "unique_sessions": 0,
            "promoted_horizons": [],
            "reason": "No persisted real Options Flow v2 snapshots yet",
        }

    stock_df = fetch_stock_data(symbol, period, "1d")
    if stock_df.empty:
        raise HTTPException(404, f"No market data for {symbol}")

    # API uses the latest persisted real observation. The Streamlit workflow uses
    # the current session snapshot that was fetched during the forecast run.
    current_snapshot = history[-1]
    result = build_options_promotion(history, stock_df, current_snapshot)
    payload = result.to_dict()
    payload["current_snapshot_source"] = "latest_persisted_real_snapshot"
    return payload
