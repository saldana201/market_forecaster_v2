"""Causal cross-market feature families for Market Forecaster 3.8."""
from __future__ import annotations
from typing import Callable, Iterable
import re
import numpy as np
import pandas as pd
from market_forecaster.core.data import fetch_stock_data

DEFAULT_CONTEXT_FAMILIES = ("broad_market", "volatility", "rates", "credit", "dollar")
ALL_CONTEXT_FAMILIES = DEFAULT_CONTEXT_FAMILIES + ("sector",)

FAMILY_DESCRIPTIONS = {
    "broad_market": "SPY and QQQ market-state returns, trend and volatility.",
    "volatility": "CBOE VIX level/change state.",
    "rates": "10-year Treasury-yield proxy (^TNX) level/change state.",
    "credit": "HYG/LQD credit-risk proxy returns and relative spread moves.",
    "dollar": "U.S. Dollar Index proxy (DX-Y.NYB) returns/trend.",
    "sector": "Optional user-supplied sector ETF context such as XLK or XLF.",
}

_SOURCE_MAP = {
    "broad_market": (("SPY", "spy", "asset"), ("QQQ", "qqq", "asset")),
    "volatility": (("^VIX", "vix", "level"),),
    "rates": (("^TNX", "tnx", "level"),),
    "credit": (("HYG", "hyg", "asset"), ("LQD", "lqd", "asset")),
    "dollar": (("DX-Y.NYB", "dxy", "asset"),),
}
_TICKER_RE = re.compile(r"^[A-Z0-9.^=_-]{1,24}$")

def _clean_close(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty or "Date" not in frame.columns:
        return pd.DataFrame(columns=["Date", "Close"])
    df = frame.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    if "Close" not in df.columns:
        return pd.DataFrame(columns=["Date", "Close"])
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    out = pd.DataFrame({
        "Date": pd.to_datetime(df["Date"], errors="coerce"),
        "Close": pd.to_numeric(close, errors="coerce"),
    })
    try:
        out["Date"] = out["Date"].dt.tz_localize(None)
    except TypeError:
        pass
    out = out.dropna(subset=["Date", "Close"]).sort_values("Date").drop_duplicates("Date", keep="last")
    out = out[out["Close"] > 0].reset_index(drop=True)
    return out

def build_source_features(source_frame: pd.DataFrame, *, prefix: str, mode: str = "asset") -> pd.DataFrame:
    src = _clean_close(source_frame)
    if src.empty:
        return pd.DataFrame()
    close = src["Close"].astype(float)
    log_close = np.log(close)
    ret1 = log_close.diff()
    out = pd.DataFrame({"source_date": src["Date"]})
    if mode == "level":
        out[f"{prefix}_level"] = close
        out[f"{prefix}_change_1"] = close.diff(1)
        out[f"{prefix}_change_5"] = close.diff(5)
        out[f"{prefix}_change_20"] = close.diff(20)
        mean20 = close.rolling(20, min_periods=20).mean()
        std20 = close.rolling(20, min_periods=20).std()
        out[f"{prefix}_z20"] = (close - mean20) / std20.replace(0, np.nan)
    else:
        for lag in (1, 5, 20):
            out[f"{prefix}_ret_{lag}"] = log_close.diff(lag)
        out[f"{prefix}_rv20"] = ret1.rolling(20, min_periods=20).std() * np.sqrt(252)
        sma20 = close.rolling(20, min_periods=20).mean()
        out[f"{prefix}_trend20"] = close / sma20 - 1.0
    return out

def align_context_source(target_frame: pd.DataFrame, source_features: pd.DataFrame, *, age_column: str, max_staleness_days: int = 7) -> pd.DataFrame:
    if source_features is None or source_features.empty:
        return target_frame.copy()
    left = target_frame.copy().sort_values("Date").reset_index(drop=True)
    left["Date"] = pd.to_datetime(left["Date"], errors="coerce")
    right = source_features.copy().sort_values("source_date").reset_index(drop=True)
    right["source_date"] = pd.to_datetime(right["source_date"], errors="coerce")
    merged = pd.merge_asof(
        left, right,
        left_on="Date", right_on="source_date",
        direction="backward",
        tolerance=pd.Timedelta(days=max(1, int(max_staleness_days))),
    )
    merged[age_column] = (merged["Date"] - merged["source_date"]).dt.total_seconds() / 86400.0
    return merged.drop(columns=["source_date"])

def family_feature_columns(frame: pd.DataFrame, family: str) -> list[str]:
    prefix = f"ctx_{family}_"
    return [
        c for c in frame.columns
        if c.startswith(prefix) and pd.api.types.is_numeric_dtype(frame[c])
    ]

def _coverage(frame: pd.DataFrame, columns: list[str]) -> float:
    if frame.empty or not columns:
        return 0.0
    return float(frame[columns].notna().any(axis=1).mean() * 100.0)

def build_market_context(
    base_feature_frame: pd.DataFrame,
    ticker: str,
    *,
    period: str = "5y",
    families: Iterable[str] = DEFAULT_CONTEXT_FAMILIES,
    sector_ticker: str | None = None,
    max_staleness_days: int = 7,
    fetcher: Callable = fetch_stock_data,
) -> tuple[pd.DataFrame, dict]:
    if base_feature_frame is None or base_feature_frame.empty:
        raise ValueError("Market context requires a non-empty target feature frame")
    target = str(ticker or "").upper().strip()
    requested = []
    for family in families:
        family = str(family).strip().lower()
        if family in ALL_CONTEXT_FAMILIES and family not in requested:
            requested.append(family)
    sector = str(sector_ticker or "").upper().strip()
    if sector and not _TICKER_RE.fullmatch(sector):
        raise ValueError(f"Invalid sector/reference ticker: {sector}")

    enriched = base_feature_frame.copy().sort_values("Date").reset_index(drop=True)
    registry = {}

    for family in requested:
        sources = ((sector, "sector", "asset"),) if family == "sector" and sector else _SOURCE_MAP.get(family, ())
        errors, used, skipped = [], [], []
        for symbol, label, mode in sources:
            if not symbol:
                continue
            if symbol.upper() == target:
                skipped.append({"symbol": symbol, "reason": "same_as_target"})
                continue
            try:
                raw = fetcher(symbol, period, "1d")
                if raw is None or raw.empty:
                    errors.append({"symbol": symbol, "error": "no_data"})
                    continue
                prefix = f"ctx_{family}_{label}"
                src = build_source_features(raw, prefix=prefix, mode=mode)
                if src.empty:
                    errors.append({"symbol": symbol, "error": "no_clean_close"})
                    continue
                enriched = align_context_source(
                    enriched, src,
                    age_column=f"{prefix}_age_days",
                    max_staleness_days=max_staleness_days,
                )
                used.append(symbol)
            except Exception as exc:
                errors.append({"symbol": symbol, "error": str(exc)})

        if family == "credit":
            for lag in (1, 5, 20):
                hyg = f"ctx_credit_hyg_ret_{lag}"
                lqd = f"ctx_credit_lqd_ret_{lag}"
                if hyg in enriched.columns and lqd in enriched.columns:
                    enriched[f"ctx_credit_spread_ret_{lag}"] = enriched[hyg] - enriched[lqd]

        if family == "sector" and "logret_5" in enriched.columns:
            sector_ret = "ctx_sector_sector_ret_5"
            if sector_ret in enriched.columns:
                enriched["ctx_sector_relative_strength_5"] = (
                    pd.to_numeric(enriched["logret_5"], errors="coerce")
                    - pd.to_numeric(enriched[sector_ret], errors="coerce")
                )

        columns = family_feature_columns(enriched, family)
        coverage = _coverage(enriched, columns)
        registry[family] = {
            "family": family,
            "description": FAMILY_DESCRIPTIONS[family],
            "available": bool(columns and coverage >= 50.0),
            "columns": columns,
            "feature_count": len(columns),
            "coverage_pct": coverage,
            "sources_used": used,
            "sources_skipped": skipped,
            "source_errors": errors,
        }

    enriched.attrs.update(getattr(base_feature_frame, "attrs", {}))
    enriched.attrs["context_families"] = registry
    return enriched, registry
