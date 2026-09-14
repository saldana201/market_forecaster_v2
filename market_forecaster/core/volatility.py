"""Causal volatility forecasting using daily market data.

This is a HAR-inspired daily proxy, not intraday realized-variance HAR. It uses
1/5/22-day lagged squared log-return averages and separate Ridge regressions for
future 1, 5, and 20-session average variance. The distinction is explicit so the
UI does not overstate the information content of daily bars.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class VolatilityForecast:
    current_annualized: float
    forecasts: dict[int, float]
    method: str
    training_rows: dict[int, int]
    as_of: pd.Timestamp

    def to_dict(self) -> dict:
        return {
            "current_annualized": self.current_annualized,
            "forecasts": {str(k): v for k, v in self.forecasts.items()},
            "method": self.method,
            "training_rows": {str(k): v for k, v in self.training_rows.items()},
            "as_of": self.as_of.isoformat(),
        }


def _frame(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "Date" not in df.columns:
        raise ValueError("Volatility engine requires market data with Date")
    close_name = "Close" if "Close" in df.columns else "Adj Close" if "Adj Close" in df.columns else None
    if close_name is None:
        raise ValueError("Volatility engine requires Close or Adj Close")
    close = df[close_name]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    out = pd.DataFrame({
        "Date": pd.to_datetime(df["Date"], errors="coerce"),
        "Close": pd.to_numeric(close, errors="coerce"),
    }).dropna().sort_values("Date").drop_duplicates("Date", keep="last")
    return out.reset_index(drop=True)


def volatility_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = _frame(df)
    ret = np.log(out["Close"]).diff()
    rv = ret.pow(2)
    out["log_return"] = ret
    out["variance_1"] = rv
    out["variance_5"] = rv.rolling(5, min_periods=3).mean()
    out["variance_22"] = rv.rolling(22, min_periods=15).mean()
    out["realized_vol_20"] = ret.rolling(20, min_periods=15).std() * np.sqrt(252)
    return out


def _future_mean(series: pd.Series, horizon: int) -> pd.Series:
    arr = np.column_stack([series.shift(-step).to_numpy(dtype=float) for step in range(1, horizon + 1)])
    valid_count = np.sum(np.isfinite(arr), axis=1)
    total = np.nansum(arr, axis=1)
    mean = np.divide(total, valid_count, out=np.full(len(series), np.nan), where=valid_count == horizon)
    return pd.Series(mean, index=series.index)


def _fit_horizon(features: pd.DataFrame, horizon: int) -> tuple[float, int] | None:
    eps = 1e-12
    work = features[["variance_1", "variance_5", "variance_22"]].copy()
    work["target"] = _future_mean(features["variance_1"], horizon)
    work = work.replace([np.inf, -np.inf], np.nan).dropna()
    if len(work) < 80:
        return None

    X = np.log(work[["variance_1", "variance_5", "variance_22"]].to_numpy(dtype=float) + eps)
    y = np.log(work["target"].to_numpy(dtype=float) + eps)
    scaler = StandardScaler().fit(X)
    model = Ridge(alpha=1.0).fit(scaler.transform(X), y)

    latest = features[["variance_1", "variance_5", "variance_22"]].dropna().iloc[-1].to_numpy(dtype=float)
    pred_log = float(model.predict(scaler.transform(np.log(latest.reshape(1, -1) + eps)))[0])
    pred_var = max(0.0, float(np.exp(pred_log) - eps))
    annualized = float(np.sqrt(pred_var * 252))
    return annualized, int(len(work))


def _ewma_fallback(features: pd.DataFrame) -> float:
    values = features["variance_1"].dropna().to_numpy(dtype=float)
    if not len(values):
        return float("nan")
    variance = float(values[0])
    lam = 0.94
    for value in values[1:]:
        variance = lam * variance + (1 - lam) * float(value)
    return float(np.sqrt(max(variance, 0.0) * 252))


def forecast_volatility(
    df: pd.DataFrame,
    horizons: Iterable[int] = (1, 5, 20),
) -> VolatilityForecast:
    features = volatility_feature_frame(df)
    if features["realized_vol_20"].dropna().empty:
        raise ValueError("Not enough history for volatility forecast")

    current = float(features["realized_vol_20"].dropna().iloc[-1])
    fallback = _ewma_fallback(features)
    forecasts: dict[int, float] = {}
    rows: dict[int, int] = {}
    used_har = False

    for horizon in sorted({int(h) for h in horizons if int(h) > 0}):
        result = _fit_horizon(features, horizon)
        if result is None:
            forecasts[horizon] = fallback
            rows[horizon] = 0
        else:
            forecasts[horizon], rows[horizon] = result
            used_har = True

    return VolatilityForecast(
        current_annualized=current,
        forecasts=forecasts,
        method="har_daily_proxy_ridge" if used_har else "ewma_94_fallback",
        training_rows=rows,
        as_of=pd.Timestamp(features["Date"].iloc[-1]),
    )
