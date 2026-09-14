"""Options Flow v2 API route."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from market_forecaster.core.options_flow_v2 import fetch_options_flow_v2

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/options/{ticker}")
async def get_options_flow(
    ticker: str,
    max_expiries: int = Query(12, ge=1, le=24),
    risk_free_rate: float | None = Query(None, ge=0.0, le=0.25),
):
    """Return the current Options Flow v2 snapshot.

    This endpoint is read-only and does not persist snapshots. The Streamlit app
    persists observed snapshots when the user explicitly enables Options Flow.
    """
    try:
        result = fetch_options_flow_v2(
            ticker,
            max_expiries=max_expiries,
            risk_free_rate=risk_free_rate,
        )
        if not result.get("available"):
            raise HTTPException(status_code=404, detail=result.get("reason", "Options data unavailable"))
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("options_flow_v2_failed ticker=%s", ticker)
        raise HTTPException(status_code=503, detail="Options provider unavailable")
