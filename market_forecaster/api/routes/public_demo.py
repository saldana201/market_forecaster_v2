"""Public cached Demo endpoints. These routes never trigger training."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from market_forecaster.core.demo_universe import as_public_rows, is_demo_ticker
from market_forecaster.services.forecast_access import CachedForecastUnavailable, load_demo_forecast

router = APIRouter()


@router.get("/public/demo-universe")
async def public_demo_universe():
    return {"symbols": as_public_rows()}


@router.get("/public/forecast-contract/{ticker}")
async def public_demo_forecast_contract(ticker: str):
    symbol = str(ticker or "").upper().strip()
    if not is_demo_ticker(symbol):
        raise HTTPException(status_code=403, detail=f"{symbol or 'Ticker'} is not available in Demo.")
    try:
        return load_demo_forecast(symbol).contract
    except CachedForecastUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
