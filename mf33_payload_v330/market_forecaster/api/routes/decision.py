"""Decision-layer API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from market_forecaster.core.decision_layer import load_decision_snapshot

router = APIRouter()


@router.get("/decision/{ticker}")
async def get_latest_decision(ticker: str):
    symbol = ticker.upper().strip()
    snapshot = load_decision_snapshot(symbol)
    if not snapshot:
        raise HTTPException(
            status_code=404,
            detail="No decision snapshot exists yet. Run a governed Ensemble forecast first.",
        )
    return snapshot
