"""Forecast API route using true OOS metrics."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from market_forecaster.api.schemas import ForecastRequestSchema, ForecastResponseSchema, MetricsSchema, SignalSchema
from market_forecaster.config import __version__
from market_forecaster.core.data import data_freshness, fetch_stock_data, infer_forecast_freq
from market_forecaster.core.ensemble import run_ensemble_forecast
from market_forecaster.core.indicators import add_technical_indicators
from market_forecaster.core.patterns import detect_chart_patterns
from market_forecaster.core.prophet_model import evaluate_oos, fit_and_forecast, prepare_for_prophet
from market_forecaster.core.seasonal import SeasonalAnalyzer
from market_forecaster.core.sentiment import SentimentAnalyzer
from market_forecaster.core.signals import compute_basic_signal

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/forecast", response_model=ForecastResponseSchema)
async def run_forecast(req: ForecastRequestSchema):
    try:
        stock_df = fetch_stock_data(req.ticker, req.period, req.interval)
        if stock_df.empty:
            raise HTTPException(404, f"No data found for {req.ticker}")
        freshness = data_freshness(stock_df)
        stock_df = add_technical_indicators(stock_df)

        # Pattern scores are snapshot signal features only. They are not copied back
        # through history as Prophet regressors.
        pattern_scores = detect_chart_patterns(stock_df)
        prophet_df = prepare_for_prophet(stock_df)
        freq = infer_forecast_freq(req.ticker, req.interval)

        model_kwargs = {
            "growth": req.growth_mode,
            "changepoint_prior_scale": req.cps,
            "seasonality_prior_scale": req.sps,
            "seasonality_mode": req.seasonality_mode,
        }

        fit_df = prophet_df.copy()
        y_min = 0.0
        y_range = 1.0
        normalize_logistic = req.growth_mode == "logistic"
        if normalize_logistic:
            y_min = float(fit_df["y"].min())
            y_range = max(float(fit_df["y"].max()) - y_min, 1.0)
            fit_df["y"] = (fit_df["y"] - y_min) / y_range
            fit_df["cap"] = 1.2
            fit_df["floor"] = 0.0

        _, forecast, contributions = fit_and_forecast(
            fit_df,
            future_days=req.horizon,
            use_options=req.use_options,
            future_freq=freq,
            **model_kwargs,
        )
        if normalize_logistic:
            for col in ("yhat", "yhat_lower", "yhat_upper"):
                forecast[col] = forecast[col] * y_range + y_min

        oos = evaluate_oos(
            prophet_df,
            holdout_days=req.holdout_days,
            model_kwargs=model_kwargs,
            use_options=req.use_options,
            growth_mode=req.growth_mode,
            normalize_logistic=normalize_logistic,
            n_folds=3,
            future_freq=freq,
        )
        metrics = MetricsSchema(
            mae=oos.get("mae"),
            rmse=oos.get("rmse"),
            mape=oos.get("mape"),
            smape=oos.get("smape"),
            directional_accuracy=oos.get("directional_accuracy"),
            evaluation_type=oos.get("evaluation_type", "out_of_sample"),
            folds=int(oos.get("n_folds", 0) or 0),
        )

        signal_result = compute_basic_signal(pattern_scores, stock_df, forecast)
        signal = SignalSchema(
            signal=signal_result.signal,
            score=signal_result.score,
            confidence=signal_result.confidence,
            components=signal_result.components,
        )

        forecast_rows = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(req.horizon)
        forecast_list = [
            {
                "date": row.ds.isoformat(),
                "yhat": round(float(row.yhat), 4),
                "yhat_lower": round(float(row.yhat_lower), 4),
                "yhat_upper": round(float(row.yhat_upper), 4),
            }
            for row in forecast_rows.itertuples(index=False)
        ]

        ensemble_data = None
        if req.use_ensemble:
            result = run_ensemble_forecast(req.ticker, stock_df, req.horizon)
            if result:
                ensemble_data = {
                    "models_used": result["models_used"],
                    "weights": result["weights"],
                    "validation_errors_smape": result["validation_errors_smape"],
                    "validation_size": result["validation_size"],
                    "interval_method": result["interval_method"],
                    "interval_half_width": result["interval_half_width"],
                    "expected_change_pct": round(
                        (float(result["ensemble"][-1]) - float(result["ensemble"][0]))
                        / float(result["ensemble"][0]) * 100,
                        2,
                    ) if float(result["ensemble"][0]) != 0 else 0.0,
                }

        sentiment_data = SentimentAnalyzer().analyze(req.ticker) if req.use_sentiment else None
        seasonal_data = SeasonalAnalyzer().get_current_signal() if req.use_seasonal else None

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
                "period": req.period,
                "interval": req.interval,
                "growth": req.growth_mode,
                "cps": req.cps,
                "sps": req.sps,
                "future_freq": freq,
            },
            data_freshness=freshness,
            model_metadata={
                "app_version": __version__,
                "primary_model": "prophet",
                "regressor_policy": "causal_lagged_technicals_pattern_snapshots_excluded",
                "evaluation": "rolling_out_of_sample",
                "regressor_contributions": contributions,
            },
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("forecast_failed ticker=%s", req.ticker)
        raise HTTPException(500, "Forecast execution failed")
