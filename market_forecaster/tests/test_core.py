"""
Market Forecaster — Tests
Run: pytest market_forecaster/tests/ -v
"""

import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta


# -------------------------------------------------------
# Config tests
# -------------------------------------------------------

class TestConfig:
    def test_forecast_request_validation(self):
        from market_forecaster.config import ForecastRequest

        req = ForecastRequest(ticker="aapl", horizon=999, cps=99.0)
        assert req.ticker == "AAPL"
        assert req.horizon == 180  # clamped
        assert req.cps == 0.50     # clamped

    def test_forecast_request_logistic(self):
        from market_forecaster.config import ForecastRequest

        req = ForecastRequest(growth_mode="linear", normalize_logistic=True)
        assert req.normalize_logistic is False  # cleared for linear

        req2 = ForecastRequest(growth_mode="logistic", normalize_logistic=True)
        assert req2.normalize_logistic is True

    def test_plan_features(self):
        from market_forecaster.config import get_plan

        trial = get_plan("trial")
        assert trial.allow_ensemble is True
        assert trial.max_tickers == 2

        starter = get_plan("starter")
        assert starter.allow_options is False
        assert starter.allow_csv is True


# -------------------------------------------------------
# Indicators tests
# -------------------------------------------------------

def _make_stock_df(n=200) -> pd.DataFrame:
    """Generate a synthetic stock DataFrame for testing."""
    dates = pd.date_range(start="2024-01-01", periods=n, freq="D")
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "Date": dates,
        "Open": close - np.random.rand(n),
        "High": close + np.random.rand(n) * 2,
        "Low": close - np.random.rand(n) * 2,
        "Close": close,
        "Volume": np.random.randint(1_000_000, 10_000_000, n),
    })


class TestIndicators:
    def test_add_indicators(self):
        from market_forecaster.core.indicators import add_technical_indicators

        df = _make_stock_df()
        result = add_technical_indicators(df)

        assert "RSI_14" in result.columns
        assert "MACD" in result.columns
        assert "SMA_20" in result.columns
        assert "vol_zscore_20" in result.columns
        assert len(result) == len(df)

    def test_empty_df(self):
        from market_forecaster.core.indicators import add_technical_indicators

        result = add_technical_indicators(pd.DataFrame())
        assert result.empty

    def test_no_volume(self):
        from market_forecaster.core.indicators import add_technical_indicators

        df = _make_stock_df().drop(columns=["Volume"])
        result = add_technical_indicators(df)
        assert result["vol_zscore_20"].isna().all()


# -------------------------------------------------------
# Patterns tests
# -------------------------------------------------------

class TestPatterns:
    def test_detect_chart_patterns(self):
        from market_forecaster.core.patterns import detect_chart_patterns

        df = _make_stock_df(300)
        scores = detect_chart_patterns(df)

        assert isinstance(scores, dict)
        assert "ascending_triangle" in scores
        assert "double_top" in scores
        assert all(0 <= v <= 1 for v in scores.values())

    def test_empty_df_patterns(self):
        from market_forecaster.core.patterns import detect_chart_patterns

        scores = detect_chart_patterns(pd.DataFrame())
        assert all(v == 0.0 for v in scores.values())

    def test_append_features(self):
        from market_forecaster.core.patterns import append_pattern_features

        df = _make_stock_df()
        result = append_pattern_features(df)
        assert "ascending_triangle" in result.columns
        assert "head_shoulders" in result.columns


# -------------------------------------------------------
# Signals tests
# -------------------------------------------------------

class TestSignals:
    def test_basic_signal(self):
        from market_forecaster.core.signals import compute_basic_signal
        from market_forecaster.core.indicators import add_technical_indicators

        df = _make_stock_df()
        df = add_technical_indicators(df)
        scores = {p: 0.0 for p in ["ascending_triangle", "bullish_flag", "double_top"]}
        forecast_df = pd.DataFrame({"ds": df["Date"], "yhat": df["Close"]})

        result = compute_basic_signal(scores, df, forecast_df)
        assert result.signal in ("BUY", "SELL", "HOLD")
        assert isinstance(result.score, float)
        assert 0 <= result.confidence <= 100

    def test_integrated_signal(self):
        from market_forecaster.core.signals import compute_integrated_signal
        from market_forecaster.core.indicators import add_technical_indicators

        df = _make_stock_df()
        df = add_technical_indicators(df)
        scores = {p: 0.0 for p in ["ascending_triangle", "double_top"]}
        forecast_df = pd.DataFrame({"ds": df["Date"], "yhat": df["Close"]})

        result = compute_integrated_signal(
            scores, df, forecast_df,
            sentiment_data={"overall_sentiment": 0.3},
            seasonal_signal={"seasonal_score": 0.1},
        )
        assert result.signal in ("STRONG BUY", "BUY", "HOLD", "SELL", "STRONG SELL")


# -------------------------------------------------------
# Seasonal tests
# -------------------------------------------------------

class TestSeasonal:
    def test_analyze_patterns(self):
        from market_forecaster.core.seasonal import SeasonalAnalyzer

        df = _make_stock_df()
        analyzer = SeasonalAnalyzer()
        result = analyzer.analyze_patterns(df)

        assert "day_of_week" in result
        assert "monthly" in result
        assert "day_of_week_best" in result

    def test_current_signal(self):
        from market_forecaster.core.seasonal import SeasonalAnalyzer

        analyzer = SeasonalAnalyzer()
        signal = analyzer.get_current_signal()

        assert "signals" in signal
        assert "seasonal_score" in signal
        assert signal["recommendation"] in ("BULLISH", "BEARISH", "NEUTRAL")


# -------------------------------------------------------
# Sentiment tests
# -------------------------------------------------------

class TestSentiment:
    def test_simulated_sentiment(self):
        from market_forecaster.core.sentiment import SentimentAnalyzer

        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("AAPL")

        assert result["is_simulated"] is True
        assert -1 <= result["overall_sentiment"] <= 1
        assert 0 <= result["fear_greed_index"] <= 100
        assert result["sentiment_label"] in ("BULLISH", "BEARISH", "NEUTRAL")


# -------------------------------------------------------
# AutoTune config store tests
# -------------------------------------------------------

class TestConfigStore:
    def test_save_and_load(self, tmp_path):
        from market_forecaster.autotune.config_store import ConfigStore

        store = ConfigStore(path=str(tmp_path / "test_configs.json"))
        store.save("AAPL", {"cps": 0.08}, {"mape": 2.3})

        result = store.get("AAPL")
        assert result is not None
        assert result["params"]["cps"] == 0.08

    def test_list_tickers(self, tmp_path):
        from market_forecaster.autotune.config_store import ConfigStore

        store = ConfigStore(path=str(tmp_path / "test_configs.json"))
        store.save("AAPL", {}, {})
        store.save("SPY", {}, {})

        assert store.list_tickers() == ["AAPL", "SPY"]

    def test_staleness(self, tmp_path):
        from market_forecaster.autotune.config_store import ConfigStore

        store = ConfigStore(path=str(tmp_path / "test_configs.json"))
        store.save("AAPL", {}, {})

        assert store.is_stale("AAPL", max_age_days=7) is False
        assert store.is_stale("MSFT") is True
