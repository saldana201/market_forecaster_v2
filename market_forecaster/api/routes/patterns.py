"""Current chart-pattern snapshot endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from market_forecaster.api.schemas import PatternResponseSchema
from market_forecaster.config import BEARISH_PATTERNS, BULLISH_PATTERNS
from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.indicators import add_technical_indicators
from market_forecaster.core.patterns import detect_chart_patterns

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/patterns/{ticker}", response_model=PatternResponseSchema)
async def get_patterns(ticker: str, period: str = Query("1y")):
    symbol = ticker.upper().strip()
    try:
        stock_df = fetch_stock_data(symbol, period, "1d")
        if stock_df.empty:
            raise HTTPException(404, f"No data for {symbol}")
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
        return PatternResponseSchema(
            ticker=symbol,
            scores=scores,
            bias=bias,
            bullish_strong=[{"pattern": p, "score": float(scores[p])} for p in BULLISH_PATTERNS if float(scores.get(p, 0) or 0) >= 0.7],
            bearish_strong=[{"pattern": p, "score": float(scores[p])} for p in BEARISH_PATTERNS if float(scores.get(p, 0) or 0) >= 0.7],
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("pattern_analysis_failed ticker=%s", symbol)
        raise HTTPException(500, "Pattern analysis failed")
