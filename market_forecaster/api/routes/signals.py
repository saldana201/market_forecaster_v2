"""Signals API route; pattern snapshots are not historical model regressors."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from market_forecaster.core.data import fetch_stock_data, infer_forecast_freq
from market_forecaster.core.ensemble import run_ensemble_forecast
from market_forecaster.core.indicators import add_technical_indicators
from market_forecaster.core.patterns import detect_chart_patterns
from market_forecaster.core.prophet_model import fit_and_forecast, prepare_for_prophet
from market_forecaster.core.seasonal import SeasonalAnalyzer
from market_forecaster.core.sentiment import SentimentAnalyzer
from market_forecaster.core.signals import compute_basic_signal, compute_integrated_signal

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/signals/{ticker}")
async def get_signals(
    ticker: str,
    period: str = Query("1y"),
    horizon: int = Query(30, ge=7, le=180),
    include_ensemble: bool = Query(False),
    include_sentiment: bool = Query(False),
    include_seasonal: bool = Query(False),
):
    symbol = ticker.upper().strip()
    try:
        stock_df = fetch_stock_data(symbol, period, "1d")
        if stock_df.empty:
            raise HTTPException(404, f"No data for {symbol}")
        stock_df = add_technical_indicators(stock_df)
        pattern_scores = detect_chart_patterns(stock_df)
        prophet_df = prepare_for_prophet(stock_df)
        model_kwargs = {
            "growth": "linear",
            "changepoint_prior_scale": 0.10,
            "seasonality_prior_scale": 8.0,
            "seasonality_mode": "multiplicative",
        }
        _, forecast, _ = fit_and_forecast(
            prophet_df,
            future_days=horizon,
            future_freq=infer_forecast_freq(symbol),
            **model_kwargs,
        )
        basic = compute_basic_signal(pattern_scores, stock_df, forecast)
        result = {
            "ticker": symbol,
            "basic_signal": {
                "signal": basic.signal,
                "score": basic.score,
                "confidence": basic.confidence,
                "components": basic.components,
            },
            "patterns": pattern_scores,
            "pattern_model_policy": "snapshot_only_not_historical_regressor",
        }

        ensemble_result = run_ensemble_forecast(symbol, stock_df, horizon) if include_ensemble else None
        sentiment_data = SentimentAnalyzer().analyze(symbol) if include_sentiment else None
        seasonal_signal = SeasonalAnalyzer().get_current_signal() if include_seasonal else None
        if any([ensemble_result, sentiment_data, seasonal_signal]):
            integrated = compute_integrated_signal(
                pattern_scores,
                stock_df,
                forecast,
                ensemble_result=ensemble_result,
                sentiment_data=sentiment_data,
                seasonal_signal=seasonal_signal,
            )
            result["integrated_signal"] = {
                "signal": integrated.signal,
                "score": integrated.score,
                "confidence": integrated.confidence,
                "components": integrated.components,
            }
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("signal_generation_failed ticker=%s", symbol)
        raise HTTPException(500, "Signal generation failed")
