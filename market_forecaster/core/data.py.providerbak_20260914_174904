"""Market data access with validation, retries, and freshness metadata."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Final

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)
_TICKER_RE: Final = re.compile(r"^[A-Z0-9.^=_-]{1,24}$")
_REQUIRED_PRICE_COLUMNS: Final = ("Open", "High", "Low", "Close")


class DataProviderError(RuntimeError):
    """Raised when a market-data provider returns unusable data."""


def normalize_ticker(ticker: str) -> str:
    value = str(ticker or "").upper().strip()
    if not value or not _TICKER_RE.fullmatch(value):
        raise ValueError("Invalid ticker symbol")
    return value


def infer_forecast_freq(ticker: str, interval: str = "1d") -> str:
    """Return a conservative pandas frequency for future forecast dates."""
    interval = str(interval or "1d").lower()
    if interval == "1wk":
        return "W-FRI"
    if interval == "1mo":
        return "ME"
    symbol = normalize_ticker(ticker)
    # Yahoo crypto pairs conventionally end in -USD; crypto trades seven days/week.
    return "D" if symbol.endswith("-USD") else "B"


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        out = df.copy()
        out.columns = [col[0] if isinstance(col, tuple) else col for col in out.columns]
        return out
    return df


def _clean_market_frame(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if df is None or df.empty:
        raise DataProviderError(f"No market data returned for {ticker}")

    out = _flatten_columns(df.reset_index())
    if "Date" not in out.columns and "Datetime" in out.columns:
        out = out.rename(columns={"Datetime": "Date"})
    if "Date" not in out.columns:
        raise DataProviderError("Provider response has no Date/Datetime column")

    out["Date"] = pd.to_datetime(out["Date"], errors="coerce", utc=True).dt.tz_localize(None)
    out = out.dropna(subset=["Date"]).sort_values("Date")
    out = out.drop_duplicates(subset=["Date"], keep="last")

    for col in _REQUIRED_PRICE_COLUMNS:
        if col not in out.columns:
            raise DataProviderError(f"Provider response missing required column: {col}")
        out[col] = pd.to_numeric(out[col], errors="coerce")
    if "Volume" in out.columns:
        out["Volume"] = pd.to_numeric(out["Volume"], errors="coerce")

    out = out.dropna(subset=["Close"])
    if out.empty:
        raise DataProviderError(f"No valid closing prices returned for {ticker}")

    out = out.reset_index(drop=True)
    out.attrs["provider"] = "yfinance"
    out.attrs["ticker"] = ticker
    out.attrs["fetched_at_utc"] = datetime.now(timezone.utc).isoformat()
    out.attrs["last_market_timestamp"] = out["Date"].max().isoformat()
    return out


def fetch_stock_data(
    ticker: str,
    period: str = "1y",
    interval: str = "1d",
    *,
    max_attempts: int = 3,
    backoff_seconds: float = 0.5,
) -> pd.DataFrame:
    """Fetch historical market data; returns an empty frame after provider failure."""
    symbol = normalize_ticker(ticker)
    last_error: Exception | None = None

    for attempt in range(1, max(1, max_attempts) + 1):
        try:
            raw = yf.download(
                symbol,
                period=period,
                interval=interval,
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            return _clean_market_frame(raw, symbol)
        except Exception as exc:  # provider exceptions vary by yfinance release
            last_error = exc
            logger.warning(
                "market_data_fetch_failed ticker=%s attempt=%s/%s error=%s",
                symbol,
                attempt,
                max_attempts,
                type(exc).__name__,
            )
            if attempt < max_attempts:
                time.sleep(backoff_seconds * (2 ** (attempt - 1)))

    logger.error("Market data unavailable for %s after retries: %s", symbol, last_error)
    return pd.DataFrame()


def data_freshness(df: pd.DataFrame) -> dict:
    if df is None or df.empty or "Date" not in df.columns:
        return {"provider": None, "fetched_at_utc": None, "last_market_timestamp": None}
    return {
        "provider": df.attrs.get("provider", "unknown"),
        "fetched_at_utc": df.attrs.get("fetched_at_utc"),
        "last_market_timestamp": df.attrs.get(
            "last_market_timestamp", pd.Timestamp(df["Date"].max()).isoformat()
        ),
    }


def fetch_options_snapshot(ticker: str) -> dict:
    """Fetch a current options snapshot. No synthetic historical series are created."""
    symbol = normalize_ticker(ticker)
    try:
        stock = yf.Ticker(symbol)
        expirations = tuple(stock.options or ())
        if not expirations:
            return {}

        call_vol = put_vol = call_oi = put_oi = 0.0
        gamma_exposure = 0.0
        unusual: list[dict] = []

        current_price = 0.0
        try:
            fast_info = stock.fast_info
            current_price = float(fast_info.get("last_price") or 0.0)
        except Exception:
            pass
        if current_price <= 0:
            hist = stock.history(period="5d", auto_adjust=False)
            if not hist.empty:
                current_price = float(pd.to_numeric(hist["Close"], errors="coerce").dropna().iloc[-1])

        for expiry in expirations[:10]:
            try:
                chain = stock.option_chain(expiry)
                for side, frame, sign in (("CALL", chain.calls, 1.0), ("PUT", chain.puts, -1.0)):
                    if frame is None or frame.empty:
                        continue
                    vol = pd.to_numeric(frame.get("volume", 0), errors="coerce").fillna(0)
                    oi = pd.to_numeric(frame.get("openInterest", 0), errors="coerce").fillna(0)
                    if side == "CALL":
                        call_vol += float(vol.sum())
                        call_oi += float(oi.sum())
                    else:
                        put_vol += float(vol.sum())
                        put_oi += float(oi.sum())

                    strikes = pd.to_numeric(frame.get("strike", 0), errors="coerce").fillna(0)
                    if current_price > 0:
                        near = (strikes > 0) & ((current_price / strikes).between(0.8, 1.2))
                        # Proxy only: OI-weighted near-money exposure, not option Greek gamma.
                        gamma_exposure += sign * float((oi[near] * 100 * (current_price * 0.01) ** 2).sum())

                    mask = (oi > 100) & (vol > 2 * oi)
                    for idx in frame.index[mask]:
                        row_oi = float(oi.loc[idx])
                        row_vol = float(vol.loc[idx])
                        unusual.append(
                            {
                                "type": side,
                                "strike": float(strikes.loc[idx]),
                                "expiry": expiry,
                                "volume": int(row_vol),
                                "oi": int(row_oi),
                                "ratio": round(row_vol / row_oi, 2) if row_oi else 0.0,
                            }
                        )
            except Exception as exc:
                logger.debug("options_expiry_skipped ticker=%s expiry=%s error=%s", symbol, expiry, exc)

        pcr_vol = put_vol / max(call_vol, 1.0)
        pcr_oi = put_oi / max(call_oi, 1.0)
        vol_sentiment = 50 * (1 - pcr_vol / (1 + pcr_vol)) + 50
        oi_sentiment = 50 * (1 - pcr_oi / (1 + pcr_oi)) + 50
        gamma_sentiment = 75 if gamma_exposure > 0 else 25 if gamma_exposure < 0 else 50
        score = vol_sentiment * 0.4 + oi_sentiment * 0.3 + gamma_sentiment * 0.3

        return {
            "put_call_volume_ratio": float(pcr_vol),
            "put_call_oi_ratio": float(pcr_oi),
            "total_call_volume": int(call_vol),
            "total_put_volume": int(put_vol),
            "total_call_oi": int(call_oi),
            "total_put_oi": int(put_oi),
            "gamma_exposure_proxy": float(gamma_exposure),
            "options_sentiment_score": float(score),
            "unusual_activities": sorted(unusual, key=lambda item: item["ratio"], reverse=True)[:10],
            "current_price": float(current_price),
            "provider": "yfinance",
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "notes": "gamma_exposure_proxy is an OI-based proxy and is not dealer-positioned Greek gamma",
        }
    except Exception as exc:
        logger.error("Options fetch failed for %s: %s", symbol, exc)
        return {}


def get_close_series(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype="float64")
    for col in ("Close", "Adj Close"):
        if col in df.columns:
            obj = df[col]
            if isinstance(obj, pd.DataFrame):
                obj = obj.iloc[:, 0]
            return pd.to_numeric(obj, errors="coerce")
    return pd.Series(dtype="float64")
