"""
Market Forecaster — Sentiment Analysis

⚠️ CURRENT IMPLEMENTATION: Simulated data for demonstration.
Production: Replace with real API integration (Alpha Vantage, Finnhub, etc.)
"""

import logging
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Flag to track whether we're using real or simulated data
_USING_REAL_API = False


class SentimentAnalyzer:
    """Market sentiment analyzer.

    Current implementation generates simulated sentiment scores.
    To integrate a real API, override the `_fetch_real_sentiment` method.
    """

    def __init__(self):
        self.is_simulated = not _USING_REAL_API

    def analyze(self, ticker: str) -> dict:
        """Analyze sentiment for a ticker."""
        if _USING_REAL_API:
            return self._fetch_real_sentiment(ticker)
        return self._generate_simulated(ticker)

    def _generate_simulated(self, ticker: str) -> dict:
        """Generate simulated sentiment (demo only)."""
        np.random.seed(hash(ticker + datetime.now().strftime("%Y%m%d")) % 2**32)

        news = np.random.uniform(-0.5, 0.5)
        social = np.random.uniform(-0.5, 0.5)
        overall = 0.6 * news + 0.4 * social
        fg = int(50 + overall * 50)

        if overall > 0.25:
            label = "BULLISH"
        elif overall < -0.25:
            label = "BEARISH"
        else:
            label = "NEUTRAL"

        return {
            "ticker": ticker,
            "overall_sentiment": round(overall, 3),
            "news_sentiment": round(news, 3),
            "social_sentiment": round(social, 3),
            "fear_greed_index": fg,
            "sentiment_label": label,
            "headlines": self._sample_headlines(ticker, news),
            "social_mentions": np.random.randint(500, 10000),
            "timestamp": datetime.now().isoformat(),
            "is_simulated": True,  # ALWAYS flag this
        }

    def _fetch_real_sentiment(self, ticker: str) -> dict:
        """
        Hook for real sentiment API integration.

        Example with Alpha Vantage:
            url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={ticker}&apikey={API_KEY}"
            response = requests.get(url)
            data = response.json()
            # Parse and return structured sentiment
        """
        raise NotImplementedError(
            "Real sentiment API not configured. "
            "Set _USING_REAL_API=True and implement _fetch_real_sentiment()."
        )

    def _sample_headlines(self, ticker: str, sentiment: float) -> list:
        positive = [
            f"{ticker} Shows Strong Momentum in Trading",
            f"Analysts Upgrade {ticker} Rating",
            f"{ticker} Beats Market Expectations",
        ]
        negative = [
            f"{ticker} Faces Headwinds Amid Market Uncertainty",
            f"Analysts Express Concerns About {ticker}",
            f"Short Interest Rises in {ticker}",
        ]
        neutral = [
            f"{ticker} Trades Sideways Amid Mixed Signals",
            f"Investors Watch {ticker} for Key Developments",
        ]

        if sentiment > 0.2:
            return positive[:2] + neutral[:1]
        elif sentiment < -0.2:
            return negative[:2] + neutral[:1]
        return neutral + positive[:1]

    def create_sentiment_features(
        self, ticker: str, start_date, end_date
    ) -> pd.DataFrame:
        """Create time series of sentiment features (simulated)."""
        if pd.isna(start_date) or pd.isna(end_date):
            return pd.DataFrame()

        dates = pd.date_range(start=start_date, end=end_date, freq="D")
        n = len(dates)
        np.random.seed(hash(ticker) % 2**32)

        # Mean-reverting random walk
        sentiment = [0.0]
        for _ in range(n - 1):
            change = np.random.normal(0, 0.1)
            sentiment.append(np.clip(sentiment[-1] * 0.95 + change, -1, 1))

        sentiment = np.array(sentiment)

        return pd.DataFrame({
            "Date": dates,
            "sentiment_score": sentiment,
            "news_sentiment": np.clip(sentiment + np.random.normal(0, 0.15, n), -1, 1),
            "social_sentiment": np.clip(sentiment + np.random.normal(0, 0.25, n), -1, 1),
            "fear_greed_index": np.clip(50 + sentiment * 30, 0, 100),
        })
