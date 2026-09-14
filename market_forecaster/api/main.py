"""Production-hardened FastAPI entry point."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from market_forecaster.api.middleware import RateLimitMiddleware, RequestContextMiddleware
from market_forecaster.api.routes import autotune as autotune_routes
from market_forecaster.api.routes import forecast as forecast_routes
from market_forecaster.api.routes import patterns as pattern_routes
from market_forecaster.api.routes import signals as signal_routes
from market_forecaster.api.routes import model_zoo as model_zoo_routes
from market_forecaster.api.routes import regime as regime_routes
from market_forecaster.api.routes import xgb as xgb_routes
from market_forecaster.api.routes import consensus as consensus_routes
from market_forecaster.api.security import require_api_key
from market_forecaster.api.settings import load_settings
from market_forecaster.config import DISCLAIMER, __version__
from market_forecaster.core.ensemble import ARIMA_AVAILABLE, LSTM_AVAILABLE
from market_forecaster.core.xgb_multihorizon import XGBOOST_AVAILABLE

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)
settings = load_settings()

app = FastAPI(
    title="Market Forecaster API",
    description=f"Multi-model market forecasting API.\n\n{DISCLAIMER}",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=settings.allow_credentials,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "X-Request-ID"],
)
app.add_middleware(
    RateLimitMiddleware,
    requests=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
)
app.add_middleware(RequestContextMiddleware)

protected = [Depends(require_api_key)]
app.include_router(forecast_routes.router, prefix="/api/v1", tags=["Forecast"], dependencies=protected)
app.include_router(signal_routes.router, prefix="/api/v1", tags=["Signals"], dependencies=protected)
app.include_router(pattern_routes.router, prefix="/api/v1", tags=["Patterns"], dependencies=protected)
app.include_router(autotune_routes.router, prefix="/api/v1", tags=["AutoTune"], dependencies=protected)
app.include_router(model_zoo_routes.router, prefix="/api/v1", tags=["Model Zoo"], dependencies=protected)
app.include_router(regime_routes.router, prefix="/api/v1", tags=["Regime"], dependencies=protected)
app.include_router(xgb_routes.router, prefix="/api/v1", tags=["XGBoost"], dependencies=protected)
app.include_router(consensus_routes.router, prefix="/api/v1", tags=["Consensus"], dependencies=protected)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
    return JSONResponse(
        status_code=422,
        content={"detail": "Request validation failed", "request_id": request_id, "errors": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
    logger.exception("unhandled_api_error request_id=%s", request_id)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )


@app.get("/api/v1/health")
async def health():
    return {
        "status": "ok",
        "version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/ready")
async def ready():
    # Import/config validation happens at module import. Report optional model state here.
    return {
        "status": "ready",
        "version": __version__,
        "environment": settings.environment,
        "auth_enabled": settings.auth_enabled,
        "models_available": {
            "prophet": True,
            "arima": ARIMA_AVAILABLE,
            "random_forest": True,
            "xgboost": XGBOOST_AVAILABLE,
            "ridge": True,
            "lstm": LSTM_AVAILABLE,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
async def root():
    return {
        "service": "Market Forecaster API",
        "version": __version__,
        "docs": "/docs",
        "health": "/api/v1/health",
        "readiness": "/api/v1/ready",
    }
