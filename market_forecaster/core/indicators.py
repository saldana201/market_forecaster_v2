"""
Market Forecaster — Technical Indicators
Pure computation, no UI dependencies.
"""

import numpy as np
import pandas as pd

from market_forecaster.core.data import get_close_series
from market_forecaster.config import TECH_FEATURE_COLUMNS


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add standard technical indicators to a stock DataFrame.

    Handles: missing Close column, duplicate columns (DataFrame vs Series),
    missing Volume column.
    """
    if df is None or df.empty:
        return df

    df = df.copy()

    close = get_close_series(df)
    if close.empty:
        return df

    # Ensure we have a usable Close column
    if "Close" not in df.columns:
        df["Close"] = close

    # --- Returns ---
    df["ret_1d"] = close.pct_change()
    df["ret_5d"] = close.pct_change(5)

    # Rolling volatility (annualized)
    df["volatility_20"] = df["ret_1d"].rolling(20, min_periods=20).std() * np.sqrt(252)

    # --- Moving averages ---
    df["SMA_20"] = close.rolling(20, min_periods=5).mean()
    df["SMA_50"] = close.rolling(50, min_periods=10).mean()
    df["SMA_200"] = close.rolling(200, min_periods=20).mean()

    # --- MACD (12, 26, 9) ---
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    df["MACD"] = macd
    df["MACD_signal"] = macd_signal
    df["MACD_hist"] = macd - macd_signal

    # --- RSI (14) ---
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(14, min_periods=14).mean()
    avg_loss = loss.rolling(14, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI_14"] = 100 - (100 / (1 + rs))

    # --- Volume z-score ---
    if "Volume" in df.columns:
        vol_obj = df["Volume"]
        if isinstance(vol_obj, pd.DataFrame):
            vol_obj = vol_obj.iloc[:, 0]
        vol = pd.to_numeric(vol_obj, errors="coerce")
        vol_mean = vol.rolling(20, min_periods=20).mean()
        vol_std = vol.rolling(20, min_periods=20).std()
        df["vol_zscore_20"] = (vol - vol_mean) / vol_std.replace(0, np.nan)
    else:
        df["vol_zscore_20"] = np.nan

    return df
