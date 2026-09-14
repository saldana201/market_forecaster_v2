"""
Market Forecaster — REST API
FastAPI service exposing forecast, signals, and patterns endpoints.

Run: uvicorn market_forecaster.api.main:app --reload --port 8000
"""

import logging
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from market_forecaster.config import __version__, DISCLAIMER
from market_forecaster.core.ensemble import ARIMA_AVAILABLE, LSTM_AVAILABLE
from market_forecaster.api.schemas import (
    ForecastRequestSchema,
    ForecastResponseSchema,
    HealthResponseSchema,
    MetricsSchema,
    PatternResponseSchema,
    SignalSchema,
)
from market_forecaster.api.routes import forecast as forecast_routes
from market_forecaster.api.routes import signals as signal_routes
from market_forecaster.api.routes import patterns as pattern_routes
from market_forecaster.api.routes import autotune as autotune_routes

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Market Forecaster API",
    description=(
        "Multi-model market forecasting API. "
        "Prophet + Ensemble (ARIMA/RF/LSTM) + Options Flow + Chart Patterns + Sentiment + Seasonal. "
        f"\n\n{DISCLAIMER}"
    ),
    version=__version__,
)

# CORS for web integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include route modules
app.include_router(forecast_routes.router, prefix="/api/v1", tags=["Forecast"])
app.include_router(signal_routes.router, prefix="/api/v1", tags=["Signals"])
app.include_router(pattern_routes.router, prefix="/api/v1", tags=["Patterns"])
app.include_router(autotune_routes.router, prefix="/api/v1", tags=["AutoTune"])


@app.get("/api/v1/health", response_model=HealthResponseSchema)
async def health():
    return HealthResponseSchema(
        status="ok",
        version=__version__,
        models_available={
            "prophet": True,
            "arima": ARIMA_AVAILABLE,
            "lstm": LSTM_AVAILABLE,
            "random_forest": True,
        },
        timestamp=datetime.utcnow().isoformat(),
    )


@app.get("/")
async def root():
    return {
        "service": "Market Forecaster API",
        "version": __version__,
        "docs": "/docs",
        "health": "/api/v1/health",
    }
