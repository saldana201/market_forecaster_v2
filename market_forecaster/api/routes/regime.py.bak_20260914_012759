"""Market regime and volatility API route."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.regime import classify_regime
from market_forecaster.core.volatility import forecast_volatility

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/regime/{ticker}")
async def get_regime(
    ticker: str,
    period: str = Query("2y"),
    interval: str = Query("1d"),
):
    """Return the current causal market regime and volatility forecast."""
    try:
        stock_df = fetch_stock_data(ticker, period, interval)
        if stock_df.empty:
            raise HTTPException(404, f"No data for {ticker.upper()}")
        regime = classify_regime(stock_df)
        volatility = forecast_volatility(stock_df)
        return {
            "ticker": ticker.upper(),
            "regime": regime.to_dict(),
            "volatility_forecast": volatility.to_dict(),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        logger.exception("regime_route_failed ticker=%s", ticker)
        raise HTTPException(500, "Regime analysis failed")
