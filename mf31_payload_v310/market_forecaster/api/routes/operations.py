"""Production operations API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.operations import operations_health, run_operations_cycle

router = APIRouter()


@router.get("/operations/{ticker}")
async def get_operations_health(ticker: str):
    return operations_health(ticker.upper().strip())


@router.post("/operations/{ticker}/run")
async def run_operations(ticker: str, period: str = Query("2y"), force: bool = Query(True)):
    symbol = ticker.upper().strip()
    stock_df = fetch_stock_data(symbol, period, "1d")
    if stock_df.empty:
        raise HTTPException(status_code=404, detail=f"No market data for {symbol}")
    cycle = run_operations_cycle(symbol, stock_df, force=force)
    return {"ticker": symbol, "cycle": cycle, "health": operations_health(symbol, stock_df)}
