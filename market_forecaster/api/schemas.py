"""
Market Forecaster — API Schemas
Pydantic models for request validation and response serialization.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ForecastRequestSchema(BaseModel):
    """Request body for /forecast endpoint."""
    ticker: str = Field(..., description="Stock ticker symbol (e.g. AAPL, SPY, ETH-USD)")
    period: str = Field("1y", description="Historical data period")
    interval: str = Field("1d", description="Data sampling interval")
    horizon: int = Field(30, ge=7, le=180, description="Forecast horizon in days")
    holdout_days: int = Field(15, ge=5, le=60, description="Holdout evaluation days")
    growth_mode: str = Field("linear", description="Prophet growth mode")
    seasonality_mode: str = Field("multiplicative", description="Seasonality mode")
    cps: float = Field(0.10, ge=0.01, le=0.50, description="Changepoint prior scale")
    sps: float = Field(8.0, ge=0.1, le=20.0, description="Seasonality prior scale")
    use_options: bool = Field(False, description="Include options flow analysis")
    use_ensemble: bool = Field(False, description="Run ensemble models")
    use_sentiment: bool = Field(False, description="Include sentiment analysis")
    use_seasonal: bool = Field(False, description="Include seasonal analysis")


class MetricsSchema(BaseModel):
    """Forecast evaluation metrics."""
    mae: Optional[float] = None
    rmse: Optional[float] = None
    mape: Optional[float] = None
    smape: Optional[float] = None
    directional_accuracy: Optional[float] = None


class SignalSchema(BaseModel):
    """Trading signal output."""
    signal: str = "HOLD"
    score: float = 0.0
    confidence: float = 0.0
    components: dict = {}


class ForecastResponseSchema(BaseModel):
    """Response from /forecast endpoint."""
    ticker: str
    horizon: int
    forecast: list[dict]  # [{date, yhat, yhat_lower, yhat_upper}]
    metrics: MetricsSchema
    signal: SignalSchema
    patterns: dict = {}
    ensemble: Optional[dict] = None
    sentiment: Optional[dict] = None
    seasonal: Optional[dict] = None
    config_used: dict = {}
    timestamp: str = ""


class PatternResponseSchema(BaseModel):
    """Response from /patterns endpoint."""
    ticker: str
    scores: dict
    bias: str
    bullish_strong: list = []
    bearish_strong: list = []


class HealthResponseSchema(BaseModel):
    """Response from /health endpoint."""
    status: str = "ok"
    version: str = ""
    models_available: dict = {}
    timestamp: str = ""
