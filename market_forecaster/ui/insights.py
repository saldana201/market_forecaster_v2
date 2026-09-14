"""
Market Forecaster — Plain-English Insights
Generates human-readable interpretation of forecast results.
"""

import numpy as np
from typing import Optional


def generate_forecast_insight(
    ticker: str,
    horizon: int,
    last_price: float,
    forecast_end: float,
    mape: float,
    signal: str,
    pattern_bias: str = "Neutral",
    rsi: Optional[float] = None,
    ensemble_change_pct: Optional[float] = None,
    sentiment_label: Optional[str] = None,
    seasonal_rec: Optional[str] = None,
) -> str:
    """
    Build a concise plain-English summary of what the forecast means.
    Designed for Simple/Trader mode users who want actionable context.
    """
    parts = []

    # --- Price direction ---
    if last_price > 0:
        change_pct = (forecast_end - last_price) / last_price * 100
        dollar_change = forecast_end - last_price

        if abs(change_pct) < 1:
            direction = "roughly flat"
        elif change_pct > 0:
            direction = f"a **{change_pct:.1f}% gain** (~${dollar_change:+.2f})"
        else:
            direction = f"a **{abs(change_pct):.1f}% decline** (~${dollar_change:+.2f})"

        parts.append(
            f"**{ticker} — {horizon}-Day Outlook:** "
            f"The model projects {direction} from ${last_price:.2f} to ${forecast_end:.2f}."
        )
    else:
        parts.append(f"**{ticker} — {horizon}-Day Outlook**")

    # --- Confidence / accuracy ---
    if not np.isnan(mape) and mape > 0:
        if mape < 3:
            fit_desc = "strong"
        elif mape < 7:
            fit_desc = "moderate"
        else:
            fit_desc = "loose"

        error_dollars = last_price * mape / 100 if last_price > 0 else 0
        parts.append(
            f"Model fit is **{fit_desc}** (MAPE: {mape:.1f}%), "
            f"meaning the actual price could differ by ~${error_dollars:.2f} on average."
        )

    # --- Signal ---
    signal_desc = {
        "STRONG BUY": "multiple indicators are aligned bullish",
        "BUY": "indicators lean bullish overall",
        "HOLD": "signals are mixed — no clear directional edge",
        "SELL": "indicators lean bearish overall",
        "STRONG SELL": "multiple indicators are aligned bearish",
    }
    parts.append(
        f"**Signal: {signal}** — {signal_desc.get(signal, 'mixed signals')}."
    )

    # --- Supporting evidence ---
    evidence = []

    if pattern_bias and pattern_bias != "Neutral":
        evidence.append(f"chart patterns are **{pattern_bias.lower()}**")

    if rsi is not None:
        if rsi < 30:
            evidence.append(f"RSI is oversold ({rsi:.0f})")
        elif rsi > 70:
            evidence.append(f"RSI is overbought ({rsi:.0f})")

    if ensemble_change_pct is not None:
        if abs(ensemble_change_pct) > 1:
            dir_word = "up" if ensemble_change_pct > 0 else "down"
            evidence.append(f"ensemble models project {dir_word} {abs(ensemble_change_pct):.1f}%")

    if sentiment_label and sentiment_label != "NEUTRAL":
        evidence.append(f"sentiment is **{sentiment_label.lower()}**")

    if seasonal_rec and seasonal_rec != "NEUTRAL":
        evidence.append(f"seasonal factors are **{seasonal_rec.lower()}**")

    if evidence:
        parts.append("**Key factors:** " + ", ".join(evidence) + ".")

    # --- Risk note ---
    parts.append(
        "_This is a model projection, not a guarantee. "
        "Use alongside your own research and risk management._"
    )

    return "\n\n".join(parts)


def pattern_bias_label(pattern_scores: dict) -> str:
    """Derive a simple Bullish/Bearish/Mixed/Neutral label from pattern scores."""
    from market_forecaster.config import BULLISH_PATTERNS, BEARISH_PATTERNS

    bull = sum(float(pattern_scores.get(p, 0) or 0) for p in BULLISH_PATTERNS)
    bear = sum(float(pattern_scores.get(p, 0) or 0) for p in BEARISH_PATTERNS)

    if bull == 0 and bear == 0:
        return "Neutral"
    if bull > bear * 1.2:
        return "Bullish"
    if bear > bull * 1.2:
        return "Bearish"
    return "Mixed"
