"""Forecast Intelligence Platform API for Market Forecaster 4.0."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from market_forecaster.core.cross_ticker_validation import validate_authority_across_tickers
from market_forecaster.core.forecast_authority import (
    load_authority_config,
    save_authority_config,
    validate_authority_config,
)
from market_forecaster.core.forecast_contract import build_forecast_contract
from market_forecaster.core.research_snapshots import load_latest_contract

router = APIRouter()


@router.get("/forecast-authority")
async def get_forecast_authority():
    config = load_authority_config(require_available_models=False)
    return {
        "config": config,
        "validation": validate_authority_config(
            config,
            require_available_models=False,
        ),
    }


@router.post("/forecast-authority")
async def update_forecast_authority(config: dict[str, Any] = Body(...)):
    try:
        saved = save_authority_config(config)
        return {"status": "saved", "config": saved}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/forecast-contract/{ticker}")
async def get_forecast_contract(
    ticker: str,
    period: str = Query("10y"),
    n_splits: int = Query(6, ge=4, le=8),
    test_size: int = Query(20, ge=15, le=40),
):
    try:
        return build_forecast_contract(
            ticker,
            period=period,
            n_splits=n_splits,
            test_size=test_size,
            persist=False,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/forecast-contract/{ticker}/snapshot")
async def create_forecast_contract_snapshot(
    ticker: str,
    period: str = Query("10y"),
    n_splits: int = Query(6, ge=4, le=8),
    test_size: int = Query(20, ge=15, le=40),
):
    try:
        return build_forecast_contract(
            ticker,
            period=period,
            n_splits=n_splits,
            test_size=test_size,
            persist=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/forecast-contract-latest/{ticker}")
async def get_latest_forecast_contract(ticker: str):
    contract = load_latest_contract(ticker)
    if contract is None:
        raise HTTPException(status_code=404, detail="No persisted Forecast Contract")
    return contract


@router.get("/research/cross-ticker-authority")
async def cross_ticker_authority_validation(
    tickers: str = Query("AAPL,MSFT,SPY,QQQ,TSLA,TMC"),
    period: str = Query("5y"),
    n_splits: int = Query(4, ge=4, le=6),
    test_size: int = Query(20, ge=15, le=30),
):
    symbols = [x.strip().upper() for x in tickers.split(",") if x.strip()]
    if not symbols:
        raise HTTPException(status_code=400, detail="At least one ticker is required")
    return validate_authority_across_tickers(
        symbols,
        period=period,
        n_splits=n_splits,
        test_size=test_size,
    )
