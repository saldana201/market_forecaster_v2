"""Pydantic contracts for the production API."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class ForecastRequestSchema(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=24)
    period: str = "1y"
    interval: str = "1d"
    horizon: int = Field(30, ge=7, le=180)
    holdout_days: int = Field(15, ge=5, le=60)
    growth_mode: str = "linear"
    seasonality_mode: str = "multiplicative"
    cps: float = Field(0.10, ge=0.01, le=0.50)
    sps: float = Field(8.0, ge=0.1, le=20.0)
    use_options: bool = False
    use_ensemble: bool = False
    use_sentiment: bool = False
    use_seasonal: bool = False

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.upper().strip()


class MetricsSchema(BaseModel):
    mae: Optional[float] = None
    rmse: Optional[float] = None
    mape: Optional[float] = None
    smape: Optional[float] = None
    directional_accuracy: Optional[float] = None
    evaluation_type: str = "out_of_sample"
    folds: int = 0


class SignalSchema(BaseModel):
    signal: str = "HOLD"
    score: float = 0.0
    confidence: float = 0.0
    components: dict[str, Any] = Field(default_factory=dict)


class ForecastResponseSchema(BaseModel):
    ticker: str
    horizon: int
    forecast: list[dict[str, Any]]
    metrics: MetricsSchema
    signal: SignalSchema
    patterns: dict[str, Any] = Field(default_factory=dict)
    ensemble: Optional[dict[str, Any]] = None
    sentiment: Optional[dict[str, Any]] = None
    seasonal: Optional[dict[str, Any]] = None
    config_used: dict[str, Any] = Field(default_factory=dict)
    data_freshness: dict[str, Any] = Field(default_factory=dict)
    model_metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = ""


class PatternResponseSchema(BaseModel):
    ticker: str
    scores: dict[str, float]
    bias: str
    bullish_strong: list[dict[str, Any]] = Field(default_factory=list)
    bearish_strong: list[dict[str, Any]] = Field(default_factory=list)


class HealthResponseSchema(BaseModel):
    status: str = "ok"
    version: str = ""
    models_available: dict[str, bool] = Field(default_factory=dict)
    timestamp: str = ""
