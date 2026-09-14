"""
Market Forecaster — Forecast API Route
"""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException

from market_forecaster.api.schemas import (
    ForecastRequestSchema,
    ForecastResponseSchema,
    MetricsSchema,
    SignalSchema,
)
from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.indicators import add_technical_indicators
from market_forecaster.core.patterns import detect_chart_patterns, append_pattern_features
from market_forecaster.core.prophet_model import prepare_for_prophet, fit_and_forecast, evaluate_holdout
from market_forecaster.core.signals import compute_basic_signal
from market_forecaster.core.ensemble import run_ensemble_forecast
from market_forecaster.core.sentiment import SentimentAnalyzer
from market_forecaster.core.seasonal import SeasonalAnalyzer

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/forecast", response_model=ForecastResponseSchema)
async def run_forecast(req: ForecastRequestSchema):
    """Run a complete forecast for a single ticker."""
    try:
        # 1. Fetch data
        stock_df = fetch_stock_data(req.ticker, req.period, req.interval)
        if stock_df.empty:
            raise HTTPException(404, f"No data found for {req.ticker}")

        stock_df = add_technical_indicators(stock_df)

        # 2. Chart patterns
        pattern_scores = detect_chart_patterns(stock_df)
        stock_df = append_pattern_features(stock_df, pattern_scores)

        # 3. Prepare Prophet data (no synthetic options)
        prophet_df = prepare_for_prophet(stock_df)

        # 4. Prophet kwargs
        model_kwargs = {
            "growth": req.growth_mode,
            "changepoint_prior_scale": req.cps,
            "seasonality_prior_scale": req.sps,
            "seasonality_mode": req.seasonality_mode,
        }

        # 5. Fit and forecast
        model, forecast, contributions = fit_and_forecast(
            prophet_df, future_days=req.horizon,
            use_options=req.use_options, **model_kwargs,
        )

        # 6. Evaluate
        metrics_dict = evaluate_holdout(prophet_df, forecast, req.holdout_days)
        metrics = MetricsSchema(
            mae=metrics_dict.get("mae"),
            rmse=metrics_dict.get("rmse"),
            mape=metrics_dict.get("mape"),
            smape=metrics_dict.get("smape"),
            directional_accuracy=metrics_dict.get("directional_accuracy"),
        )

        # 7. Signal
        signal_result = compute_basic_signal(pattern_scores, stock_df, forecast)
        signal = SignalSchema(
            signal=signal_result.signal,
            score=signal_result.score,
            confidence=signal_result.confidence,
            components=signal_result.components,
        )

        # 8. Format forecast output
        forecast_rows = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(req.horizon)
        forecast_list = [
            {
                "date": row["ds"].isoformat(),
                "yhat": round(row["yhat"], 2),
                "yhat_lower": round(row["yhat_lower"], 2),
                "yhat_upper": round(row["yhat_upper"], 2),
            }
            for _, row in forecast_rows.iterrows()
        ]

        # 9. Optional models
        ensemble_data = None
        if req.use_ensemble:
            try:
                result = run_ensemble_forecast(req.ticker, stock_df, req.horizon)
                if result:
                    ensemble_data = {
                        "models_used": result["models_used"],
                        "expected_change_pct": round(
                            (result["ensemble"][-1] - result["ensemble"][0]) / result["ensemble"][0] * 100, 2
                        ) if result["ensemble"][0] != 0 else 0,
                    }
            except Exception as e:
                logger.warning(f"Ensemble failed: {e}")

        sentiment_data = None
        if req.use_sentiment:
            try:
                analyzer = SentimentAnalyzer()
                sentiment_data = analyzer.analyze(req.ticker)
            except Exception as e:
                logger.warning(f"Sentiment failed: {e}")

        seasonal_data = None
        if req.use_seasonal:
            try:
                seasonal = SeasonalAnalyzer()
                seasonal_data = seasonal.get_current_signal()
            except Exception as e:
                logger.warning(f"Seasonal failed: {e}")

        return ForecastResponseSchema(
            ticker=req.ticker,
            horizon=req.horizon,
            forecast=forecast_list,
            metrics=metrics,
            signal=signal,
            patterns=pattern_scores,
            ensemble=ensemble_data,
            sentiment=sentiment_data,
            seasonal=seasonal_data,
            config_used={
                "period": req.period, "interval": req.interval,
                "growth": req.growth_mode, "cps": req.cps, "sps": req.sps,
            },
            timestamp=datetime.utcnow().isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Forecast failed for {req.ticker}: {e}", exc_info=True)
        raise HTTPException(500, f"Forecast failed: {str(e)}")
