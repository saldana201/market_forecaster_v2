"""Opportunity-ranking API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from market_forecaster.core.opportunity_ranking import (
    load_ranking_snapshot,
    load_watchlist,
    rank_watchlist,
)

router = APIRouter()


@router.get("/opportunity-ranking")
async def get_opportunity_ranking(
    tickers: str | None = Query(None, description="Comma-separated ticker symbols"),
    include_correlation: bool = Query(True),
    max_single_risk_budget_pct: float = Query(25.0, ge=5.0, le=30.0),
):
    symbols = tickers if tickers else load_watchlist()
    if not symbols:
        raise HTTPException(
            status_code=400,
            detail="No tickers supplied and no saved opportunity watchlist exists.",
        )
    return rank_watchlist(
        symbols,
        include_correlation=include_correlation,
        max_single_risk_budget_pct=max_single_risk_budget_pct,
    )


@router.get("/opportunity-ranking/latest")
async def get_latest_opportunity_ranking():
    result = load_ranking_snapshot()
    if not result:
        raise HTTPException(status_code=404, detail="No ranking snapshot exists yet.")
    return result
