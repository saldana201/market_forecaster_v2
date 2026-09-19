"""Feature-ablation research API for Market Forecaster 3.8."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.feature_store import build_feature_store
from market_forecaster.core.feature_ablation import (
    DEFAULT_ABLATION_MODELS,
    run_feature_ablation,
)
from market_forecaster.core.market_context import (
    DEFAULT_CONTEXT_FAMILIES,
    build_market_context,
)

router = APIRouter()


@router.get("/research/feature-ablation/{ticker}")
async def feature_ablation(
    ticker: str,
    period: str = Query("5y"),
    families: str = Query(",".join(DEFAULT_CONTEXT_FAMILIES)),
    models: str = Query(",".join(DEFAULT_ABLATION_MODELS)),
    sector_ticker: str | None = Query(None),
    n_splits: int = Query(5, ge=3, le=8),
    test_size: int = Query(20, ge=10, le=40),
):
    symbol = ticker.upper().strip()
    family_list = [x.strip().lower() for x in families.split(",") if x.strip()]
    model_list = [x.strip().lower() for x in models.split(",") if x.strip()]

    market = fetch_stock_data(symbol, period, "1d")
    if market.empty:
        raise HTTPException(status_code=404, detail="No market data available")

    base, metadata = build_feature_store(market, symbol)
    enriched, registry = build_market_context(
        base,
        symbol,
        period=period,
        families=family_list,
        sector_ticker=sector_ticker,
    )
    result = run_feature_ablation(
        base,
        enriched,
        registry,
        families=family_list,
        models=model_list,
        n_splits=n_splits,
        test_size=test_size,
    )
    result["ticker"] = symbol
    result["dataset_metadata"] = metadata.to_dict()
    return result
