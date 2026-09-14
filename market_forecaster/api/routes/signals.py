"""
Market Forecaster — Signals API Route
"""

import logging
from fastapi import APIRouter, HTTPException, Query

from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.indicators import add_technical_indicators
from market_forecaster.core.patterns import detect_chart_patterns, append_pattern_features
from market_forecaster.core.prophet_model import prepare_for_prophet, fit_and_forecast
from market_forecaster.core.signals import compute_basic_signal, compute_integrated_signal
from market_forecaster.core.ensemble import run_ensemble_forecast
from market_forecaster.core.sentiment import SentimentAnalyzer
from market_forecaster.core.seasonal import SeasonalAnalyzer

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/signals/{ticker}")
async def get_signals(
    ticker: str,
    period: str = Query("1y", description="History period"),
    horizon: int = Query(30, ge=7, le=180),
    include_ensemble: bool = Query(False),
    include_sentiment: bool = Query(False),
    include_seasonal: bool = Query(False),
):
    """Get current trading signals for a ticker."""
    try:
        ticker = ticker.upper().strip()
        stock_df = fetch_stock_data(ticker, period, "1d")
        if stock_df.empty:
            raise HTTPException(404, f"No data for {ticker}")

        stock_df = add_technical_indicators(stock_df)
        pattern_scores = detect_chart_patterns(stock_df)
        stock_df = append_pattern_features(stock_df, pattern_scores)

        prophet_df = prepare_for_prophet(stock_df)

        model_kwargs = {
            "growth": "linear",
            "changepoint_prior_scale": 0.10,
            "seasonality_prior_scale": 8.0,
            "seasonality_mode": "multiplicative",
        }

        _, forecast, _ = fit_and_forecast(
            prophet_df, future_days=horizon, **model_kwargs,
        )

        # Basic signal
        basic = compute_basic_signal(pattern_scores, stock_df, forecast)

        result = {
            "ticker": ticker,
            "basic_signal": {
                "signal": basic.signal,
                "score": basic.score,
                "confidence": basic.confidence,
                "components": basic.components,
            },
            "patterns": pattern_scores,
        }

        # Optional: integrated signal
        ensemble_result = None
        sentiment_data = None
        seasonal_signal = None

        if include_ensemble:
            try:
                ensemble_result = run_ensemble_forecast(ticker, stock_df, horizon)
            except Exception as e:
                logger.warning(f"Ensemble failed: {e}")

        if include_sentiment:
            try:
                sentiment_data = SentimentAnalyzer().analyze(ticker)
            except Exception as e:
                logger.warning(f"Sentiment failed: {e}")

        if include_seasonal:
            try:
                seasonal_signal = SeasonalAnalyzer().get_current_signal()
            except Exception as e:
                logger.warning(f"Seasonal failed: {e}")

        if any([ensemble_result, sentiment_data, seasonal_signal]):
            integrated = compute_integrated_signal(
                pattern_scores, stock_df, forecast,
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
    except Exception as e:
        logger.error(f"Signal generation failed for {ticker}: {e}", exc_info=True)
        raise HTTPException(500, str(e))
