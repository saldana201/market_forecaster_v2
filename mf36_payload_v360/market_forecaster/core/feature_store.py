"""Point-in-time causal feature store for Market Forecaster 3.6."""
from __future__ import annotations
import hashlib
from dataclasses import dataclass, asdict
from typing import Iterable
import numpy as np
import pandas as pd
from market_forecaster.core.targets import DEFAULT_RESEARCH_HORIZONS, add_forward_return_targets

FEATURE_SCHEMA_VERSION = "3.6-price-volume-v1"

@dataclass(frozen=True)
class FeatureStoreMetadata:
    ticker: str
    schema_version: str
    row_count: int
    first_date: str | None
    last_date: str | None
    provider: str | None
    provider_failover_used: bool
    cache_used: bool
    feature_count: int
    dataset_hash: str
    def to_dict(self) -> dict:
        return asdict(self)

def _series(df: pd.DataFrame, name: str) -> pd.Series:
    if name not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype="float64")
    value = df[name]
    if isinstance(value, pd.DataFrame):
        value = value.iloc[:, 0]
    return pd.to_numeric(value, errors="coerce")

def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1/window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1/window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - 100.0 / (1.0 + rs)

def _dataset_hash(frame: pd.DataFrame, feature_cols: list[str]) -> str:
    cols = ["Date", "Close", *feature_cols]
    material = frame[[c for c in cols if c in frame.columns]].copy()
    raw = material.to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%S").encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def research_feature_columns(frame: pd.DataFrame) -> list[str]:
    excluded = {
        "Date", "ticker", "feature_asof", "feature_schema_version",
        "Open", "High", "Low", "Close", "Volume",
    }
    return [
        c for c in frame.columns
        if c not in excluded and not c.startswith("target_")
        and pd.api.types.is_numeric_dtype(frame[c])
    ]

def build_feature_store(stock_df: pd.DataFrame, ticker: str, *, horizons: Iterable[int] = DEFAULT_RESEARCH_HORIZONS):
    if stock_df is None or stock_df.empty or "Date" not in stock_df.columns:
        raise ValueError("Feature store requires non-empty market data with Date")
    attrs = dict(getattr(stock_df, "attrs", {}))
    df = stock_df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    base = pd.DataFrame({
        "Date": pd.to_datetime(df["Date"], errors="coerce"),
        "Open": _series(df, "Open"),
        "High": _series(df, "High"),
        "Low": _series(df, "Low"),
        "Close": _series(df, "Close"),
        "Volume": _series(df, "Volume"),
    })
    try:
        base["Date"] = base["Date"].dt.tz_localize(None)
    except TypeError:
        pass
    base = base.dropna(subset=["Date", "Close"]).sort_values("Date").drop_duplicates("Date", keep="last")
    base = base[base["Close"] > 0].reset_index(drop=True)
    if len(base) < 30:
        raise ValueError("Research feature store requires at least 30 clean rows")

    close = base["Close"].astype(float)
    log_close = np.log(close)
    ret1 = log_close.diff()

    for lag in (1,2,3,5,10,20,60):
        base[f"logret_{lag}"] = log_close.diff(lag)
    for win in (5,10,20,60):
        base[f"rv_{win}"] = ret1.rolling(win, min_periods=win).std() * np.sqrt(252)
        downside = ret1.where(ret1 < 0, 0.0)
        base[f"downside_rv_{win}"] = downside.rolling(win, min_periods=win).std() * np.sqrt(252)
    for win in (5,20,50,200):
        sma = close.rolling(win, min_periods=win).mean()
        base[f"close_sma_{win}"] = close / sma - 1.0

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    base["macd_pct"] = macd / close
    base["macd_hist_pct"] = (macd - macd_signal) / close
    base["rsi_14"] = _rsi(close) / 100.0

    open_ = base["Open"].replace(0, np.nan)
    high = base["High"]
    low = base["Low"]
    base["range_pct"] = (high-low) / close
    base["open_close_pct"] = (close-open_) / open_
    base["gap_pct"] = open_ / close.shift(1) - 1.0
    span = (high-low).replace(0, np.nan)
    base["close_location"] = (close-low) / span

    volume = base["Volume"].replace(0, np.nan)
    for win in (5,20,60):
        mean = volume.rolling(win, min_periods=win).mean()
        std = volume.rolling(win, min_periods=win).std()
        base[f"volume_z_{win}"] = (volume-mean) / std.replace(0, np.nan)
    base["volume_log_change"] = np.log(volume).diff()
    base["dollar_volume_log"] = np.log((volume*close).replace(0, np.nan))

    dow = base["Date"].dt.dayofweek.astype(float)
    base["dow_sin"] = np.sin(2*np.pi*dow/7.0)
    base["dow_cos"] = np.cos(2*np.pi*dow/7.0)
    month = base["Date"].dt.month.astype(float)
    base["month_sin"] = np.sin(2*np.pi*month/12.0)
    base["month_cos"] = np.cos(2*np.pi*month/12.0)

    base["ticker"] = str(ticker or "").upper().strip()
    base["feature_asof"] = base["Date"]
    base["feature_schema_version"] = FEATURE_SCHEMA_VERSION
    out = add_forward_return_targets(base, horizons=horizons)
    features = research_feature_columns(out)
    meta = FeatureStoreMetadata(
        ticker=str(ticker or "").upper().strip(),
        schema_version=FEATURE_SCHEMA_VERSION,
        row_count=len(out),
        first_date=None if out.empty else pd.Timestamp(out["Date"].min()).isoformat(),
        last_date=None if out.empty else pd.Timestamp(out["Date"].max()).isoformat(),
        provider=attrs.get("provider"),
        provider_failover_used=bool(attrs.get("provider_failover_used", False)),
        cache_used=bool(attrs.get("is_cached", False)),
        feature_count=len(features),
        dataset_hash=_dataset_hash(out, features),
    )
    out.attrs.update(attrs)
    out.attrs["feature_store_metadata"] = meta.to_dict()
    return out, meta

def assert_point_in_time_integrity(frame: pd.DataFrame) -> dict:
    problems = []
    if frame is None or frame.empty:
        return {"status":"FAIL","problems":["empty dataset"]}
    if "Date" not in frame.columns or "feature_asof" not in frame.columns:
        problems.append("Date/feature_asof missing")
    else:
        dates = pd.to_datetime(frame["Date"], errors="coerce")
        asof = pd.to_datetime(frame["feature_asof"], errors="coerce")
        if dates.isna().any() or asof.isna().any():
            problems.append("invalid timestamps")
        if (asof > dates).any():
            problems.append("feature availability occurs after observation date")
        if not dates.is_monotonic_increasing:
            problems.append("dates are not monotonic")
        if dates.duplicated().any():
            problems.append("duplicate observation dates")
    features = research_feature_columns(frame)
    if not features:
        problems.append("no research features")
    schema = frame["feature_schema_version"].iloc[0] if "feature_schema_version" in frame.columns else "UNKNOWN"
    return {"status":"PASS" if not problems else "FAIL","problems":problems,"rows":len(frame),"features":len(features),"schema_version":schema}
