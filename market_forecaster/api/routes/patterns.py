"""
Market Forecaster — Patterns API Route
"""

import logging
from fastapi import APIRouter, HTTPException, Query

from market_forecaster.api.schemas import PatternResponseSchema
from market_forecaster.config import BULLISH_PATTERNS, BEARISH_PATTERNS
from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.indicators import add_technical_indicators
from market_forecaster.core.patterns import detect_chart_patterns

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/patterns/{ticker}", response_model=PatternResponseSchema)
async def get_patterns(
    ticker: str,
    period: str = Query("1y", description="History period"),
):
    """Get chart pattern analysis for a ticker."""
    try:
        ticker = ticker.upper().strip()
        stock_df = fetch_stock_data(ticker, period, "1d")
        if stock_df.empty:
            raise HTTPException(404, f"No data for {ticker}")

        stock_df = add_technical_indicators(stock_df)
        scores = detect_chart_patterns(stock_df)

        bull = sum(float(scores.get(p, 0) or 0) for p in BULLISH_PATTERNS)
        bear = sum(float(scores.get(p, 0) or 0) for p in BEARISH_PATTERNS)

        if bull == 0 and bear == 0:
            bias = "Neutral"
        elif bull > bear * 1.2:
            bias = "Bullish"
        elif bear > bull * 1.2:
            bias = "Bearish"
        else:
            bias = "Mixed"

        bullish_strong = [
            {"pattern": p, "score": float(scores.get(p, 0))}
            for p in BULLISH_PATTERNS if float(scores.get(p, 0) or 0) >= 0.7
        ]
        bearish_strong = [
            {"pattern": p, "score": float(scores.get(p, 0))}
            for p in BEARISH_PATTERNS if float(scores.get(p, 0) or 0) >= 0.7
        ]

        return PatternResponseSchema(
            ticker=ticker,
            scores=scores,
            bias=bias,
            bullish_strong=bullish_strong,
            bearish_strong=bearish_strong,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pattern analysis failed for {ticker}: {e}", exc_info=True)
        raise HTTPException(500, str(e))
