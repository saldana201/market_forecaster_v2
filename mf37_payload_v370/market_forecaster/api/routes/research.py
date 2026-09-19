"""Forecast-research / Model Tournament API for Market Forecaster 3.7."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.feature_store import build_feature_store
from market_forecaster.core.experiment_runner import DEFAULT_MODELS, run_research_experiment
from market_forecaster.core.model_tournament import model_registry

router = APIRouter()


@router.get("/research/models")
async def get_research_models():
    return {"models": model_registry()}


@router.get("/research/experiment/{ticker}")
async def run_experiment(
    ticker: str,
    period: str = Query("5y"),
    n_splits: int = Query(5, ge=3, le=8),
    test_size: int = Query(20, ge=10, le=40),
    models: str | None = Query(None, description="Comma-separated model names"),
    sequence_lookback: int = Query(20, ge=10, le=60),
    deep_epochs: int = Query(15, ge=1, le=40),
):
    symbol = ticker.upper().strip()
    market = fetch_stock_data(symbol, period, "1d")
    if market.empty:
        raise HTTPException(status_code=404, detail="No market data available")

    selected = (
        [x.strip().lower() for x in models.split(",") if x.strip()]
        if models else list(DEFAULT_MODELS)
    )
    features, metadata = build_feature_store(market, symbol)
    result = run_research_experiment(
        features,
        models=selected,
        n_splits=n_splits,
        test_size=test_size,
        sequence_lookback=sequence_lookback,
        deep_epochs=deep_epochs,
    )
    result["ticker"] = symbol
    result["dataset_metadata"] = metadata.to_dict()
    return result
