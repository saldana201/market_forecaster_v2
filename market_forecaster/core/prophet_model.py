"""Prophet forecasting with causal regressors and true out-of-sample evaluation."""

from __future__ import annotations

import logging
from typing import Iterable, Optional

import numpy as np
import pandas as pd
from prophet import Prophet
from sklearn.metrics import mean_absolute_error, mean_squared_error

from market_forecaster.config import TECH_FEATURE_COLUMNS

logger = logging.getLogger(__name__)

_OPTION_REGRESSORS = (
    "put_call_ratio",
    "put_call_volume_ratio",
    "gamma_exposure",
    "gamma_exposure_proxy",
    "options_sentiment",
    "options_sentiment_score",
    "oi_ratio",
    "put_call_oi_ratio",
    "unusual_activity",
)


def _ensure_1d(obj) -> pd.Series:
    if isinstance(obj, pd.Series):
        return obj.reset_index(drop=True)
    if isinstance(obj, (pd.Index, pd.DatetimeIndex)):
        return pd.Series(obj)
    if isinstance(obj, pd.DataFrame):
        return obj.iloc[:, 0].reset_index(drop=True) if obj.shape[1] else pd.Series(dtype="float64")
    return pd.Series(obj)


def _date_series(df: pd.DataFrame) -> pd.Series:
    for candidate in ("Date", "Datetime", "ds"):
        if candidate in df.columns:
            return pd.to_datetime(_ensure_1d(df[candidate]), errors="coerce", utc=True).dt.tz_localize(None)
    if isinstance(df.index, pd.DatetimeIndex):
        return pd.to_datetime(pd.Series(df.index), errors="coerce", utc=True).dt.tz_localize(None)
    raise ValueError("No date column found")


def prepare_for_prophet(
    df: pd.DataFrame,
    options_df: Optional[pd.DataFrame] = None,
    *,
    lag_regressors: bool = True,
) -> pd.DataFrame:
    """Build a causal Prophet frame.

    Production rules:
    - price-derived technical regressors are shifted one row by default so y[t]
      never uses an indicator that requires close[t].
    - chart-pattern snapshot scores are intentionally NOT included as historical
      regressors; the current pattern detector is snapshot-oriented and would leak
      information if copied backward across history.
    - real historical options data may be merged, and is shifted one row by default.
    - no backward filling is performed.
    """
    if df is None or df.empty:
        raise ValueError("Empty dataframe")

    ds = _date_series(df)
    close_col = next((c for c in ("Close", "Adj Close", "y") if c in df.columns), None)
    if close_col is None:
        raise ValueError("No Close column found")
    y = pd.to_numeric(_ensure_1d(df[close_col]), errors="coerce")

    base = pd.DataFrame({"ds": ds.values, "y": y.values})

    feature_frame = pd.DataFrame({"ds": ds.values})
    for col in TECH_FEATURE_COLUMNS:
        if col in df.columns:
            feature_frame[col] = pd.to_numeric(_ensure_1d(df[col]), errors="coerce").values

    out = base.merge(feature_frame, on="ds", how="left")
    out = out.dropna(subset=["ds", "y"]).sort_values("ds").drop_duplicates("ds", keep="last")

    tech_cols = [c for c in TECH_FEATURE_COLUMNS if c in out.columns]
    if lag_regressors and tech_cols:
        out[tech_cols] = out[tech_cols].shift(1)

    if options_df is not None and not options_df.empty:
        opt = options_df.copy()
        opt["ds"] = _date_series(opt)
        keep = ["ds"] + [c for c in _OPTION_REGRESSORS if c in opt.columns]
        opt = opt[keep].dropna(subset=["ds"]).sort_values("ds").drop_duplicates("ds", keep="last")
        out = out.merge(opt, on="ds", how="left")
        option_cols = [c for c in _OPTION_REGRESSORS if c in out.columns]
        if lag_regressors and option_cols:
            out[option_cols] = out[option_cols].shift(1)
        if option_cols:
            out[option_cols] = out[option_cols].ffill()

    out = out.reset_index(drop=True)
    if out.empty:
        raise ValueError("No valid rows after cleaning")
    return out


def _future_dates(last_date: pd.Timestamp, periods: int, freq: str) -> pd.DatetimeIndex:
    if periods <= 0:
        return pd.DatetimeIndex([])
    return pd.date_range(start=pd.Timestamp(last_date) + pd.Timedelta(days=1), periods=periods, freq=freq)


def fit_and_forecast(
    data: pd.DataFrame,
    future_days: int = 30,
    use_options: bool = False,
    *,
    future_freq: str = "D",
    future_dates: Optional[Iterable] = None,
    **model_kwargs,
) -> tuple:
    """Fit Prophet and forecast using only information available at fit time."""
    frame = data.copy().sort_values("ds").reset_index(drop=True)
    model = Prophet(**model_kwargs)

    scaled_regs: list[str] = []
    reg_source: dict[str, str] = {}

    option_cols = [c for c in _OPTION_REGRESSORS if use_options and c in frame.columns]
    tech_cols = [c for c in TECH_FEATURE_COLUMNS if c in frame.columns]

    for reg in option_cols:
        numeric = pd.to_numeric(frame[reg], errors="coerce").ffill()
        mu, sd = float(numeric.mean()), float(numeric.std())
        sd = 1.0 if not np.isfinite(sd) or sd == 0 else sd
        scaled = f"opt__{reg}"
        frame[scaled] = (numeric - mu) / sd
        model.add_regressor(scaled, mode="multiplicative")
        scaled_regs.append(scaled)
        reg_source[scaled] = reg

    for reg in tech_cols:
        numeric = pd.to_numeric(frame[reg], errors="coerce").ffill()
        mu, sd = float(numeric.mean()), float(numeric.std())
        sd = 1.0 if not np.isfinite(sd) or sd == 0 else sd
        scaled = f"tech__{reg}"
        frame[scaled] = (numeric - mu) / sd
        model.add_regressor(scaled, mode="additive")
        scaled_regs.append(scaled)
        reg_source[scaled] = reg

    fit_cols = ["ds", "y"] + scaled_regs
    if "cap" in frame.columns:
        fit_cols.append("cap")
    if "floor" in frame.columns:
        fit_cols.append("floor")

    # Forward fill is causal; remaining warm-up NaNs are dropped, never backfilled.
    if scaled_regs:
        frame[scaled_regs] = frame[scaled_regs].ffill()
    data_fit = frame[fit_cols].dropna(subset=["ds", "y"] + scaled_regs).copy()
    if len(data_fit) < 30:
        raise ValueError("Insufficient causal training rows after indicator warm-up")

    model.fit(data_fit)

    history_dates = data_fit[["ds"]].copy()
    if future_dates is None:
        dates = _future_dates(data_fit["ds"].iloc[-1], future_days, future_freq)
    else:
        dates = pd.to_datetime(pd.Series(list(future_dates)), errors="coerce").dropna()
        dates = pd.DatetimeIndex(dates).tz_localize(None) if getattr(dates, "tz", None) else pd.DatetimeIndex(dates)

    future = pd.concat(
        [history_dates, pd.DataFrame({"ds": dates})], ignore_index=True
    ).drop_duplicates("ds", keep="last").sort_values("ds").reset_index(drop=True)

    if "cap" in data_fit.columns:
        future["cap"] = float(data_fit["cap"].iloc[-1])
    if "floor" in data_fit.columns:
        future["floor"] = float(data_fit["floor"].iloc[-1])

    if scaled_regs:
        known = data_fit[["ds"] + scaled_regs]
        future = future.merge(known, on="ds", how="left")
        # Future regressor values are persistence forecasts. This is explicit and causal.
        future[scaled_regs] = future[scaled_regs].ffill()
        if future[scaled_regs].isna().any().any():
            raise ValueError("Regressor values unavailable for forecast frame")

    forecast = model.predict(future)

    contributions: dict[str, float] = {}
    horizon = max(0, len(dates))
    for scaled in scaled_regs:
        if scaled in forecast.columns:
            tail = forecast[scaled].tail(horizon) if horizon else forecast[scaled]
            value = float(tail.mean()) if not tail.empty else 0.0
            contributions[reg_source.get(scaled, scaled)] = 0.0 if not np.isfinite(value) else value

    return model, forecast, contributions


def _metrics(y: np.ndarray, yhat: np.ndarray) -> dict:
    y = np.asarray(y, dtype=float)
    yhat = np.asarray(yhat, dtype=float)
    valid = np.isfinite(y) & np.isfinite(yhat)
    y, yhat = y[valid], yhat[valid]
    if not len(y):
        return _empty_metrics()

    mae = float(mean_absolute_error(y, yhat))
    rmse = float(np.sqrt(mean_squared_error(y, yhat)))
    nz = np.where(y == 0, np.nan, y)
    mape = float(np.nanmean(np.abs((y - yhat) / nz)) * 100)
    denom = np.where((np.abs(y) + np.abs(yhat)) == 0, np.nan, (np.abs(y) + np.abs(yhat)) / 2)
    smape = float(np.nanmean(np.abs(y - yhat) / denom) * 100)
    direction = float(np.mean(np.sign(np.diff(y)) == np.sign(np.diff(yhat))) * 100) if len(y) > 1 else np.nan
    return {"mae": mae, "rmse": rmse, "mape": mape, "smape": smape, "directional_accuracy": direction}


def evaluate_holdout(prophet_df: pd.DataFrame, forecast_df: pd.DataFrame, holdout_days: int = 15) -> dict:
    """Legacy in-sample diagnostic. Do not expose as production OOS performance."""
    merged = pd.merge(
        forecast_df[["ds", "yhat"]], prophet_df[["ds", "y"]], on="ds", how="inner"
    ).sort_values("ds")
    sample = merged.tail(holdout_days).copy() if holdout_days > 0 else merged.copy()
    if sample.empty:
        result = _empty_metrics()
    else:
        result = _metrics(sample["y"].to_numpy(), sample["yhat"].to_numpy())
    result.update({"holdout_days": len(sample), "merged_df": merged, "evaluation_type": "in_sample_diagnostic"})
    return result


def evaluate_oos(
    full_df: pd.DataFrame,
    holdout_days: int,
    model_kwargs: dict,
    use_options: bool = False,
    growth_mode: str = "linear",
    normalize_logistic: bool = False,
    n_folds: int = 3,
    future_freq: str = "D",
) -> dict:
    """Rolling out-of-sample evaluation. Holdout rows are never used to fit a fold."""
    if full_df is None or full_df.empty or holdout_days <= 0:
        return _empty_metrics()

    df = full_df.sort_values("ds").drop_duplicates("ds", keep="last").reset_index(drop=True).copy()
    min_train = max(90, holdout_days * 3)
    fold_results: list[dict] = []

    for fold in range(max(1, n_folds)):
        split_idx = len(df) - holdout_days * (fold + 1)
        if split_idx < min_train:
            break
        train = df.iloc[:split_idx].copy()
        test = df.iloc[split_idx: split_idx + holdout_days].copy()
        if train.empty or test.empty:
            continue

        test_actual = test[["ds", "y"]].copy()
        y_min = 0.0
        y_range = 1.0
        if growth_mode == "logistic" and normalize_logistic:
            y_min = float(train["y"].min())
            y_max = float(train["y"].max())
            y_range = max(y_max - y_min, 1.0)
            train["y"] = (train["y"] - y_min) / y_range
            train["cap"] = 1.2
            train["floor"] = 0.0

        try:
            _, forecast, _ = fit_and_forecast(
                train,
                future_days=len(test),
                use_options=use_options,
                future_freq=future_freq,
                future_dates=test["ds"],
                **model_kwargs,
            )
            pred = forecast[["ds", "yhat"]].merge(test_actual, on="ds", how="inner")
            if growth_mode == "logistic" and normalize_logistic:
                pred["yhat"] = pred["yhat"] * y_range + y_min
            if pred.empty:
                continue
            fold_metric = _metrics(pred["y"].to_numpy(), pred["yhat"].to_numpy())
            fold_metric["merged_df"] = pred
            fold_metric["fold"] = fold
            fold_results.append(fold_metric)
        except Exception as exc:
            logger.warning("oos_fold_failed fold=%s error=%s", fold, exc)

    if not fold_results:
        result = _empty_metrics()
        result["evaluation_type"] = "out_of_sample"
        return result

    def avg(key: str) -> float:
        return float(np.nanmean([m[key] for m in fold_results]))

    mape_values = [m["mape"] for m in fold_results]
    latest = fold_results[0]
    result = {
        "mae": avg("mae"),
        "rmse": avg("rmse"),
        "mape": avg("mape"),
        "smape": avg("smape"),
        "directional_accuracy": avg("directional_accuracy"),
        "mae_mean": avg("mae"),
        "rmse_mean": avg("rmse"),
        "mape_mean": avg("mape"),
        "mape_std": float(np.nanstd(mape_values)),
        "smape_mean": avg("smape"),
        "directional_accuracy_mean": avg("directional_accuracy"),
        "n_folds": len(fold_results),
        "stability_score": float(avg("mape") + 0.25 * np.nanstd(mape_values)),
        "holdout_days": holdout_days,
        "merged_df": latest["merged_df"],
        "evaluation_type": "out_of_sample",
    }
    return result


def _empty_metrics() -> dict:
    return {
        "mae": np.nan,
        "rmse": np.nan,
        "mape": np.nan,
        "smape": np.nan,
        "directional_accuracy": np.nan,
        "holdout_days": 0,
        "merged_df": pd.DataFrame(),
    }
