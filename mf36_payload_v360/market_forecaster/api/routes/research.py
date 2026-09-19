"""Research-foundation API for Market Forecaster 3.6."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query
from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.feature_store import build_feature_store
from market_forecaster.core.experiment_runner import run_research_experiment
router=APIRouter()

@router.get("/research/experiment/{ticker}")
async def run_experiment(ticker: str, period: str=Query("5y"), n_splits: int=Query(5,ge=3,le=8), test_size: int=Query(20,ge=10,le=40)):
    symbol=ticker.upper().strip()
    market=fetch_stock_data(symbol,period,"1d")
    if market.empty: raise HTTPException(status_code=404,detail="No market data available")
    features,metadata=build_feature_store(market,symbol)
    result=run_research_experiment(features,n_splits=n_splits,test_size=test_size)
    result["ticker"]=symbol
    result["dataset_metadata"]=metadata.to_dict()
    return result
