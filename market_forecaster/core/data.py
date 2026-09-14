"""
Market Forecaster — Data Fetching
Handles stock price and options chain data retrieval.
No Streamlit dependency — can be used from API or CLI.
"""

import logging
from datetime import timedelta

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_stock_data(
    ticker: str, period: str = "1y", interval: str = "1d"
) -> pd.DataFrame:
    """
    Fetch historical stock data with clean Date column.

    Returns a DataFrame with columns: Date, Open, High, Low, Close, Volume, etc.
    Date is timezone-naive datetime64. Empty DataFrame on failure.
    """
    try:
        df = yf.download(
            ticker, period=period, interval=interval,
            auto_adjust=False, progress=False,
        )

        if df.empty:
            logger.warning(f"No data returned for {ticker}")
            return pd.DataFrame()

        df = df.reset_index()

        # Normalize date column name
        if "Date" not in df.columns and "Datetime" in df.columns:
            df = df.rename(columns={"Datetime": "Date"})

        if "Date" not in df.columns:
            logger.error(f"No Date column found for {ticker}")
            return pd.DataFrame()

        # Ensure datetime type
        if not pd.api.types.is_datetime64_any_dtype(df["Date"]):
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

        # Clean NaT rows
        nat_count = df["Date"].isna().sum()
        if nat_count == len(df):
            return pd.DataFrame()
        if nat_count > 0:
            df = df.dropna(subset=["Date"])

        # Strip timezone
        try:
            if hasattr(df["Date"].dt, "tz") and df["Date"].dt.tz is not None:
                df["Date"] = df["Date"].dt.tz_localize(None)
        except Exception:
            pass

        # Deduplicate
        if df["Date"].duplicated().any():
            df = df.drop_duplicates(subset=["Date"], keep="first")

        # Flatten MultiIndex columns if yfinance returns them
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [
                col[0] if isinstance(col, tuple) else col
                for col in df.columns
            ]

        return df.reset_index(drop=True)

    except Exception as e:
        logger.error(f"Error fetching data for {ticker}: {e}")
        return pd.DataFrame()


def fetch_options_snapshot(ticker: str) -> dict:
    """
    Fetch current options chain snapshot for a ticker.

    Returns aggregated metrics: put/call ratios, gamma exposure,
    sentiment score, unusual activity. Returns empty dict on failure.
    """
    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options

        if not expirations:
            return {}

        total_call_volume = 0
        total_put_volume = 0
        total_call_oi = 0
        total_put_oi = 0
        total_gamma_exposure = 0.0
        unusual_activities = []

        current_price = stock.info.get("regularMarketPrice", 0)
        if current_price == 0:
            hist = stock.history(period="1d")
            if not hist.empty:
                current_price = float(hist["Close"].iloc[-1])

        for exp_date in expirations[:10]:
            try:
                chain = stock.option_chain(exp_date)
                calls, puts = chain.calls, chain.puts

                if calls.empty or puts.empty:
                    continue

                total_call_volume += calls["volume"].fillna(0).sum()
                total_put_volume += puts["volume"].fillna(0).sum()
                total_call_oi += calls["openInterest"].fillna(0).sum()
                total_put_oi += puts["openInterest"].fillna(0).sum()

                # Simplified gamma exposure (near-the-money only)
                for _, row in calls.iterrows():
                    strike = row.get("strike", 0)
                    oi = row.get("openInterest", 0) or 0
                    if current_price > 0 and strike > 0:
                        moneyness = current_price / strike
                        if 0.8 < moneyness < 1.2:
                            total_gamma_exposure += oi * 100 * (current_price * 0.01) ** 2

                for _, row in puts.iterrows():
                    strike = row.get("strike", 0)
                    oi = row.get("openInterest", 0) or 0
                    if current_price > 0 and strike > 0:
                        moneyness = current_price / strike
                        if 0.8 < moneyness < 1.2:
                            total_gamma_exposure -= oi * 100 * (current_price * 0.01) ** 2

                # Unusual activity detection (volume > 2x OI)
                for side, frame in [("CALL", calls), ("PUT", puts)]:
                    for _, row in frame.iterrows():
                        vol = row.get("volume", 0) or 0
                        oi = row.get("openInterest", 0) or 0
                        if oi > 100 and vol > 2 * oi:
                            unusual_activities.append({
                                "type": side,
                                "strike": row["strike"],
                                "expiry": exp_date,
                                "volume": vol,
                                "oi": oi,
                                "ratio": round(vol / oi, 2) if oi > 0 else 0,
                            })
            except Exception as e:
                logger.debug(f"Skipping expiry {exp_date}: {e}")
                continue

        # Compute derived metrics
        pcr_vol = total_put_volume / max(total_call_volume, 1)
        pcr_oi = total_put_oi / max(total_call_oi, 1)

        vol_sentiment = 50 * (1 - pcr_vol / (1 + pcr_vol)) + 50
        oi_sentiment = 50 * (1 - pcr_oi / (1 + pcr_oi)) + 50
        gamma_sentiment = 75 if total_gamma_exposure > 0 else 25 if total_gamma_exposure < 0 else 50

        overall_sentiment = vol_sentiment * 0.4 + oi_sentiment * 0.3 + gamma_sentiment * 0.3

        def _safe(v, default=0):
            return default if pd.isna(v) else v

        return {
            "put_call_volume_ratio": _safe(pcr_vol, 1.0),
            "put_call_oi_ratio": _safe(pcr_oi, 1.0),
            "total_call_volume": int(total_call_volume),
            "total_put_volume": int(total_put_volume),
            "total_call_oi": int(total_call_oi),
            "total_put_oi": int(total_put_oi),
            "gamma_exposure": _safe(total_gamma_exposure, 0),
            "options_sentiment_score": _safe(overall_sentiment, 50),
            "unusual_activities": sorted(unusual_activities, key=lambda x: x["ratio"], reverse=True)[:10],
            "current_price": _safe(current_price, 0),
        }

    except Exception as e:
        logger.error(f"Options fetch failed for {ticker}: {e}")
        return {}


def get_close_series(df: pd.DataFrame) -> pd.Series:
    """Extract a clean 1-D Close price series from a stock DataFrame."""
    if df is None or df.empty:
        return pd.Series(dtype="float64")

    for col in ("Close", "Adj Close"):
        if col in df.columns:
            obj = df[col]
            if isinstance(obj, pd.DataFrame):
                obj = obj.iloc[:, 0]
            return pd.to_numeric(obj, errors="coerce")

    return pd.Series(dtype="float64")
