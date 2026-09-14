"""
Market Forecaster — Signal Generation
Combines technical, pattern, options, ensemble, sentiment, and seasonal signals.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from market_forecaster.config import BULLISH_PATTERNS, BEARISH_PATTERNS

logger = logging.getLogger(__name__)


@dataclass
class SignalResult:
    """Structured output from signal computation."""
    signal: str = "HOLD"          # BUY / SELL / HOLD / STRONG BUY / STRONG SELL
    score: float = 0.0
    confidence: float = 0.0
    components: dict = field(default_factory=dict)
    explanation: str = ""


def compute_basic_signal(
    pattern_scores: dict,
    tech_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    window: int = 1,
) -> SignalResult:
    """Conservative BUY/SELL/HOLD signal from patterns + technicals + options."""

    score = 0.0
    components = {}

    # --- RSI ---
    try:
        rsi_col = tech_df.get("RSI_14")
        if rsi_col is not None:
            if isinstance(rsi_col, pd.DataFrame):
                rsi_col = rsi_col.iloc[:, 0]
            rsi = float(rsi_col.iloc[-window:].mean())
            if rsi < 30:
                score += 1.0
                components["rsi"] = 1.0
            elif rsi > 70:
                score -= 1.0
                components["rsi"] = -1.0
            else:
                components["rsi"] = 0.0
    except Exception:
        pass

    # --- MACD ---
    try:
        macd_col = tech_df.get("MACD_hist")
        if macd_col is not None:
            if isinstance(macd_col, pd.DataFrame):
                macd_col = macd_col.iloc[:, 0]
            macd_hist = float(macd_col.iloc[-window:].mean())
            score += 0.5 if macd_hist > 0 else -0.5
            components["macd"] = 0.5 if macd_hist > 0 else -0.5
    except Exception:
        pass

    # --- Trend (Close vs SMA20) ---
    try:
        sma_col = tech_df.get("SMA_20")
        close_col = tech_df.get("Close")
        if sma_col is not None and close_col is not None:
            if isinstance(sma_col, pd.DataFrame):
                sma_col = sma_col.iloc[:, 0]
            if isinstance(close_col, pd.DataFrame):
                close_col = close_col.iloc[:, 0]
            trend_up = 1 if float(close_col.iloc[-1]) > float(sma_col.iloc[-1]) else -1
            score += trend_up * 0.5
            components["trend"] = trend_up * 0.5
    except Exception:
        pass

    # --- Options (if available in forecast_df) ---
    try:
        if "options_sentiment_scaled" in forecast_df.columns:
            sentiment = float(forecast_df["options_sentiment_scaled"].iloc[-window:].mean())
            score += sentiment * 0.7
        if "put_call_ratio_scaled" in forecast_df.columns:
            pcr = float(forecast_df["put_call_ratio_scaled"].iloc[-window:].mean())
            score -= pcr * 0.6
    except Exception:
        pass

    # --- Pattern bias ---
    bull = sum(float(pattern_scores.get(p, 0) or 0) for p in BULLISH_PATTERNS)
    bear = sum(float(pattern_scores.get(p, 0) or 0) for p in BEARISH_PATTERNS)
    pattern_bias = bull - bear
    score += pattern_bias * 1.8
    components["pattern_bias"] = round(pattern_bias, 2)

    # --- Final signal ---
    if score >= 1.2:
        signal = "BUY"
    elif score <= -1.2:
        signal = "SELL"
    else:
        signal = "HOLD"

    return SignalResult(
        signal=signal,
        score=round(score, 3),
        confidence=min(100, abs(score) / 1.2 * 100),
        components=components,
    )


def compute_integrated_signal(
    pattern_scores: dict,
    tech_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    ensemble_result: Optional[dict] = None,
    sentiment_data: Optional[dict] = None,
    seasonal_signal: Optional[dict] = None,
    window: int = 1,
) -> SignalResult:
    """
    Comprehensive signal combining all model outputs.

    Weights:
        Technical: 20%, Patterns: 15%, Options: 15%,
        Ensemble: 20%, Sentiment: 15%, Seasonal: 15%
    """
    weights = {
        "patterns": 0.15, "technical": 0.20, "options": 0.15,
        "ensemble": 0.20, "sentiment": 0.15, "seasonal": 0.15,
    }
    scores = {}

    # Pattern score
    bull = sum(float(pattern_scores.get(p, 0) or 0) for p in BULLISH_PATTERNS)
    bear = sum(float(pattern_scores.get(p, 0) or 0) for p in BEARISH_PATTERNS)
    scores["patterns"] = np.clip((bull - bear) / 5, -1, 1)

    # Technical score
    tech_score = 0.0
    try:
        rsi_col = tech_df.get("RSI_14")
        if rsi_col is not None:
            if isinstance(rsi_col, pd.DataFrame):
                rsi_col = rsi_col.iloc[:, 0]
            rsi = float(rsi_col.iloc[-window:].mean())
            tech_score += 0.5 if rsi < 30 else -0.5 if rsi > 70 else 0

        macd_col = tech_df.get("MACD_hist")
        if macd_col is not None:
            if isinstance(macd_col, pd.DataFrame):
                macd_col = macd_col.iloc[:, 0]
            tech_score += 0.3 if float(macd_col.iloc[-window:].mean()) > 0 else -0.3

        sma_col = tech_df.get("SMA_20")
        close_col = tech_df.get("Close")
        if sma_col is not None and close_col is not None:
            if isinstance(sma_col, pd.DataFrame):
                sma_col = sma_col.iloc[:, 0]
            if isinstance(close_col, pd.DataFrame):
                close_col = close_col.iloc[:, 0]
            tech_score += 0.2 if float(close_col.iloc[-1]) > float(sma_col.iloc[-1]) else -0.2
    except Exception:
        pass
    scores["technical"] = np.clip(tech_score, -1, 1)

    # Options score
    options_score = 0.0
    try:
        if "options_sentiment_scaled" in forecast_df.columns:
            options_score += float(forecast_df["options_sentiment_scaled"].iloc[-window:].mean()) * 0.5
        if "put_call_ratio_scaled" in forecast_df.columns:
            options_score -= float(forecast_df["put_call_ratio_scaled"].iloc[-window:].mean()) * 0.5
    except Exception:
        pass
    scores["options"] = np.clip(options_score, -1, 1)

    # Ensemble score
    if ensemble_result and "ensemble" in ensemble_result:
        forecast = ensemble_result["ensemble"]
        if len(forecast) > 1 and forecast[0] != 0:
            change = (forecast[-1] - forecast[0]) / forecast[0]
            scores["ensemble"] = float(np.clip(change * 10, -1, 1))
        else:
            scores["ensemble"] = 0.0
    else:
        scores["ensemble"] = 0.0

    # Sentiment score
    if sentiment_data and "overall_sentiment" in sentiment_data:
        scores["sentiment"] = float(np.clip(sentiment_data["overall_sentiment"] * 2, -1, 1))
    else:
        scores["sentiment"] = 0.0

    # Seasonal score
    if seasonal_signal and "seasonal_score" in seasonal_signal:
        scores["seasonal"] = float(np.clip(seasonal_signal["seasonal_score"] * 5, -1, 1))
    else:
        scores["seasonal"] = 0.0

    # Weighted overall
    overall = sum(scores[k] * weights[k] for k in weights)

    if overall >= 0.5:
        signal = "STRONG BUY"
    elif overall >= 0.25:
        signal = "BUY"
    elif overall <= -0.5:
        signal = "STRONG SELL"
    elif overall <= -0.25:
        signal = "SELL"
    else:
        signal = "HOLD"

    confidence = min(100, abs(overall) / 0.5 * 100)

    return SignalResult(
        signal=signal,
        score=round(overall, 3),
        confidence=round(confidence, 1),
        components=scores,
    )
