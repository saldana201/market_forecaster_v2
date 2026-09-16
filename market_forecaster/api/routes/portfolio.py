"""Portfolio state + position-aware ranking API."""
from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Query

from market_forecaster.core.opportunity_ranking import (
    load_ranking_snapshot,
    rank_watchlist,
)
from market_forecaster.core.portfolio import (
    build_portfolio_aware_ranking,
    load_portfolio_overlay,
    load_portfolio_state,
    save_portfolio_state,
)

router = APIRouter()


class PositionInput(BaseModel):
    ticker: str
    quantity: float
    cost_basis: float = Field(gt=0)


class PortfolioStateInput(BaseModel):
    cash: float = Field(ge=0)
    positions: list[PositionInput] = []


@router.get("/portfolio/state")
async def get_portfolio_state():
    return load_portfolio_state()


@router.post("/portfolio/state")
async def set_portfolio_state(request: PortfolioStateInput):
    try:
        return save_portfolio_state(
            request.cash,
            [position.model_dump() for position in request.positions],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/portfolio/ranking")
async def get_portfolio_ranking(
    tickers: str | None = Query(
        None,
        description="Optional comma-separated watchlist; otherwise use latest 3.4 ranking",
    ),
    include_correlation: bool = Query(True),
    max_position_pct: float = Query(20.0, ge=5.0, le=40.0),
    max_correlated_cluster_pct: float = Query(40.0, ge=15.0, le=70.0),
    correlation_threshold: float = Query(0.70, ge=0.50, le=0.90),
):
    if tickers:
        base = rank_watchlist(
            tickers,
            include_correlation=include_correlation,
        )
    else:
        base = load_ranking_snapshot()

    if not base:
        raise HTTPException(
            status_code=404,
            detail="No 3.4 ranking exists yet. Run opportunity ranking first.",
        )

    return build_portfolio_aware_ranking(
        base,
        load_portfolio_state(),
        max_position_pct=max_position_pct,
        max_correlated_cluster_pct=max_correlated_cluster_pct,
        correlation_threshold=correlation_threshold,
        include_portfolio_correlation=include_correlation,
    )


@router.get("/portfolio/ranking/latest")
async def get_latest_portfolio_ranking():
    result = load_portfolio_overlay()
    if not result:
        raise HTTPException(
            status_code=404,
            detail="No portfolio-aware ranking exists yet.",
        )
    return result
