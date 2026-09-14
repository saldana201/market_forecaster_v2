"""Forecast audit and model-governance API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.forecast_audit import audit_snapshot, reconcile_matured_outcomes

router = APIRouter()


@router.get("/audit/{ticker}")
async def get_audit(ticker: str):
    return audit_snapshot(ticker.upper().strip())


@router.post("/audit/{ticker}/reconcile")
async def reconcile_audit(
    ticker: str,
    period: str = Query("2y", description="Market history used to resolve matured targets"),
):
    symbol = ticker.upper().strip()
    stock_df = fetch_stock_data(symbol, period, "1d")
    if stock_df.empty:
        raise HTTPException(404, f"No market data for {symbol}")
    reconciliation = reconcile_matured_outcomes(symbol, stock_df)
    return {"ticker": symbol, "reconciliation": reconciliation, "audit": audit_snapshot(symbol)}
