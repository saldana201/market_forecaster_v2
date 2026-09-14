"""
Market Forecaster — Seasonal & Earnings Pattern Analysis
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from market_forecaster.core.data import get_close_series

logger = logging.getLogger(__name__)


class SeasonalAnalyzer:
    """Seasonal and earnings pattern analyzer."""

    EARNINGS_SEASONS = {
        "Q1": [(4, 1), (4, 30)],
        "Q2": [(7, 1), (7, 31)],
        "Q3": [(10, 1), (10, 31)],
        "Q4": [(1, 15), (2, 15)],
    }

    def analyze_patterns(self, df: pd.DataFrame, price_col: str = "Close") -> dict:
        """Analyze historical seasonal patterns from price data."""
        df = df.copy()
        if "Date" not in df.columns:
            return {}

        dates = pd.to_datetime(df["Date"])
        close = get_close_series(df)
        if close.empty:
            return {}

        df["returns"] = close.pct_change()
        df["dow"] = dates.dt.dayofweek
        df["month"] = dates.dt.month

        dow_returns = df.groupby("dow")["returns"].mean()
        monthly_returns = df.groupby("month")["returns"].mean()

        dow_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

        return {
            "day_of_week": {
                dow_names[i]: float(dow_returns.get(i, 0)) for i in range(5)
            },
            "day_of_week_best": dow_names[int(dow_returns.idxmax())] if len(dow_returns) > 0 else "N/A",
            "day_of_week_worst": dow_names[int(dow_returns.idxmin())] if len(dow_returns) > 0 else "N/A",
            "monthly": {int(k): float(v) for k, v in monthly_returns.to_dict().items()},
            "monthly_best": int(monthly_returns.idxmax()) if len(monthly_returns) > 0 else 1,
            "monthly_worst": int(monthly_returns.idxmin()) if len(monthly_returns) > 0 else 1,
        }

    def get_current_signal(self, date=None) -> dict:
        """Get current seasonal signal."""
        if date is None:
            date = pd.Timestamp.now()

        signals = []
        score = 0.0

        # Day of week
        dow = date.dayofweek
        if dow == 0:
            signals.append("Monday — historically weaker performance")
            score -= 0.1
        elif dow == 4:
            signals.append("Friday — potential weekend positioning")
            score += 0.05

        # Month effects
        month = date.month
        if month == 1:
            signals.append("January Effect — historically bullish for small caps")
            score += 0.15
        elif month == 12:
            signals.append("December — Santa Claus Rally potential")
            score += 0.1
        elif 5 <= month <= 10:
            signals.append("'Sell in May' period — historically weaker returns")
            score -= 0.05

        # Quarter end
        if date.is_quarter_end:
            signals.append("Quarter end — institutional window dressing")
            score += 0.1

        # Earnings season
        for q, ((sm, _), (em, _)) in self.EARNINGS_SEASONS.items():
            if sm <= month <= em:
                signals.append(f"Earnings season ({q}) — increased volatility expected")
                break

        rec = "BULLISH" if score > 0.1 else "BEARISH" if score < -0.1 else "NEUTRAL"

        return {
            "date": date.isoformat(),
            "signals": signals,
            "seasonal_score": round(score, 3),
            "recommendation": rec,
        }

    def compute_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add seasonal feature columns to a DataFrame."""
        df = df.copy()
        if "Date" in df.columns:
            dates = pd.to_datetime(df["Date"])
        elif "ds" in df.columns:
            dates = pd.to_datetime(df["ds"])
        else:
            return df

        df["day_of_week"] = dates.dt.dayofweek
        df["is_monday"] = (df["day_of_week"] == 0).astype(int)
        df["is_friday"] = (df["day_of_week"] == 4).astype(int)
        df["month"] = dates.dt.month
        df["quarter"] = dates.dt.quarter
        df["is_month_end"] = dates.dt.is_month_end.astype(int)
        df["is_quarter_end"] = dates.dt.is_quarter_end.astype(int)
        df["january_effect"] = (df["month"] == 1).astype(int)
        df["sell_in_may"] = ((df["month"] >= 5) & (df["month"] <= 10)).astype(int)
        df["santa_rally"] = (
            ((df["month"] == 12) & (dates.dt.day >= 25))
            | ((df["month"] == 1) & (dates.dt.day <= 2))
        ).astype(int)

        return df
