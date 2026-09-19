"""Canonical multi-horizon forecasting targets for Market Forecaster 3.6."""
from __future__ import annotations
from typing import Iterable
import numpy as np
import pandas as pd

DEFAULT_RESEARCH_HORIZONS = (1, 5, 10, 20)

def _clean_base(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        raise ValueError("Target generation requires a non-empty frame")
    if "Date" not in frame.columns or "Close" not in frame.columns:
        raise ValueError("Target generation requires Date and Close columns")
    out = frame.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [c[0] if isinstance(c, tuple) else c for c in out.columns]
    close = out["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce")
    try:
        out["Date"] = out["Date"].dt.tz_localize(None)
    except TypeError:
        pass
    out["Close"] = pd.to_numeric(close, errors="coerce")
    out = out.dropna(subset=["Date", "Close"]).sort_values("Date").drop_duplicates("Date", keep="last")
    out = out[out["Close"] > 0].reset_index(drop=True)
    if out.empty:
        raise ValueError("No valid positive closing prices remain")
    return out

def add_forward_return_targets(frame: pd.DataFrame, horizons: Iterable[int] = DEFAULT_RESEARCH_HORIZONS) -> pd.DataFrame:
    out = _clean_base(frame)
    horizons = sorted({int(h) for h in horizons if int(h) > 0})
    if not horizons:
        raise ValueError("At least one positive horizon is required")
    close = out["Close"].astype(float)
    log_close = np.log(close)
    for horizon in horizons:
        suffix = f"{horizon}d"
        future_close = close.shift(-horizon)
        future_date = out["Date"].shift(-horizon)
        log_return = log_close.shift(-horizon) - log_close
        out[f"target_log_return_{suffix}"] = log_return
        out[f"target_simple_return_{suffix}"] = future_close / close - 1.0
        out[f"target_direction_{suffix}"] = np.where(log_return.notna(), (log_return > 0).astype(float), np.nan)
        out[f"target_price_{suffix}"] = future_close
        out[f"target_end_date_{suffix}"] = future_date
    return out

def target_columns(horizon: int) -> dict[str, str]:
    suffix = f"{int(horizon)}d"
    return {
        "log_return": f"target_log_return_{suffix}",
        "simple_return": f"target_simple_return_{suffix}",
        "direction": f"target_direction_{suffix}",
        "price": f"target_price_{suffix}",
        "end_date": f"target_end_date_{suffix}",
    }

def reconstruct_price(anchor_price: float, predicted_log_return: float) -> float:
    anchor = float(anchor_price)
    ret = float(predicted_log_return)
    if not (np.isfinite(anchor) and anchor > 0 and np.isfinite(ret)):
        return float("nan")
    return float(anchor * np.exp(ret))
