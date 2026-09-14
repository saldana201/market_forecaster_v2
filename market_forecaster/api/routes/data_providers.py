from __future__ import annotations
from fastapi import APIRouter, Query
from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.data_providers import compare_market_data_providers, provider_runtime_summary
router=APIRouter()
@router.get("/data-providers/{ticker}")
async def provider_status(ticker:str,period:str=Query("1y"),interval:str=Query("1d")):
    frame=fetch_stock_data(ticker.upper().strip(),period,interval)
    return {"ticker":ticker.upper().strip(),"period":period,"interval":interval,"runtime":provider_runtime_summary(frame)}
@router.get("/data-providers/{ticker}/compare")
async def compare_providers(ticker:str,period:str=Query("1y"),interval:str=Query("1d")):
    return compare_market_data_providers(ticker.upper().strip(),period,interval)
