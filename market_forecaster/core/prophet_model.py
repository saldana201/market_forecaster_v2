"""
Market Forecaster — Prophet Model
Fit, forecast, and evaluate with proper train/test separation.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
from prophet import Prophet
from sklearn.metrics import mean_absolute_error, mean_squared_error

from market_forecaster.config import (
    TECH_FEATURE_COLUMNS, PATTERN_FEATURE_COLUMNS,
)

logger = logging.getLogger(__name__)


def _ensure_1d(obj) -> pd.Series:
    """Return a 1-D Series from various input types."""
    if isinstance(obj, pd.Series):
        return obj
    if isinstance(obj, (pd.Index, pd.DatetimeIndex)):
        return pd.Series(obj)
    if isinstance(obj, pd.DataFrame):
        return obj.iloc[:, 0] if obj.shape[1] > 0 else pd.Series(dtype="float64")
    return pd.Series(obj)


def prepare_for_prophet(
    df: pd.DataFrame,
    options_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Prepare a clean (ds, y) DataFrame for Prophet with optional regressors.

    NOTE: Options features from a current snapshot should NOT be fabricated
    into historical time series. Only pass real historical options data.
    """
    if df is None or len(df) == 0:
        raise ValueError("Empty dataframe")

    # Find date column
    date_col = None
    for cand in ("Date", "Datetime"):
        if cand in df.columns:
            date_col = cand
            break
    if date_col is None and isinstance(df.index, pd.DatetimeIndex):
        ds = pd.Series(df.index)
    elif date_col:
        ds = _ensure_1d(df[date_col])
    else:
        raise ValueError("No date column found")

    ds = pd.to_datetime(ds, errors="coerce").dt.tz_localize(None)

    # Find price column
    for col in ("Close", "Adj Close"):
        if col in df.columns:
            y = pd.to_numeric(_ensure_1d(df[col]), errors="coerce")
            break
    else:
        raise ValueError("No Close column found")

    out = pd.DataFrame({"ds": ds.values, "y": y.values})
    out = out.dropna(subset=["ds", "y"]).sort_values("ds").reset_index(drop=True)

    # Attach technical indicators
    for col in TECH_FEATURE_COLUMNS:
        if col in df.columns:
            series = pd.to_numeric(_ensure_1d(df[col]), errors="coerce")
            if len(series) == len(out):
                out[col] = series.values
            else:
                out[col] = series.reindex(out.index).values
            out[col] = out[col].ffill().bfill().fillna(0)

    # Attach pattern features
    for col in PATTERN_FEATURE_COLUMNS:
        if col in df.columns:
            series = pd.to_numeric(_ensure_1d(df[col]), errors="coerce")
            if len(series) == len(out):
                out[col] = series.values
            else:
                out[col] = series.reindex(out.index).values
            out[col] = out[col].ffill().bfill().fillna(0)

    # Merge real historical options data (if provided)
    if options_df is not None and not options_df.empty:
        opt = options_df.copy()
        for c in ("Date", "Datetime"):
            if c in opt.columns:
                opt = opt.rename(columns={c: "ds"})
                break
        if "ds" in opt.columns:
            opt["ds"] = pd.to_datetime(_ensure_1d(opt["ds"]), errors="coerce").dt.tz_localize(None)
            opt = opt.dropna(subset=["ds"])
            out = pd.merge(out, opt, on="ds", how="left")
            for col in opt.columns:
                if col != "ds" and col in out.columns:
                    out[col] = out[col].ffill().bfill().fillna(0)

    if out.empty:
        raise ValueError("No valid rows after cleaning")

    return out


def fit_and_forecast(
    data: pd.DataFrame,
    future_days: int = 30,
    use_options: bool = False,
    **model_kwargs,
) -> tuple:
    """
    Fit Prophet and forecast.

    Returns: (model, forecast_df, regressor_contributions)
    """
    m = Prophet(**model_kwargs)
    regressors_scaled = []
    tech_scaled = []
    pattern_regs = []

    # --- Options regressors (only if real data present) ---
    if use_options:
        opt_cols = ["put_call_ratio", "gamma_exposure", "options_sentiment", "oi_ratio", "unusual_activity"]
        for reg in opt_cols:
            if reg in data.columns and not data[reg].isna().all():
                data[reg] = data[reg].ffill().bfill()
                mu, sd = data[reg].mean(), data[reg].std()
                sd = 1.0 if pd.isna(sd) or sd == 0 else sd
                sc = f"{reg}_scaled"
                data[sc] = ((data[reg] - mu) / sd).fillna(0)
                m.add_regressor(sc, mode="multiplicative")
                regressors_scaled.append(sc)

    # --- Technical indicators ---
    for reg in TECH_FEATURE_COLUMNS:
        if reg in data.columns:
            data[reg] = data[reg].ffill().bfill()
            mu, sd = data[reg].mean(), data[reg].std()
            sd = 1.0 if pd.isna(sd) or sd == 0 else sd
            sc = f"ti_{reg}"
            data[sc] = ((data[reg] - mu) / sd).fillna(0)
            m.add_regressor(sc, mode="additive")
            tech_scaled.append(sc)

    # --- Pattern regressors (already 0-1) ---
    for reg in PATTERN_FEATURE_COLUMNS:
        if reg in data.columns:
            data[reg] = data[reg].ffill().bfill().fillna(0)
            m.add_regressor(reg, mode="multiplicative")
            pattern_regs.append(reg)

    # Skip first 2 rows (indicator warm-up)
    data_fit = data.iloc[2:].copy()
    all_cols = ["ds", "y"] + regressors_scaled + tech_scaled + pattern_regs
    for col in all_cols:
        if col in data_fit.columns:
            data_fit[col] = data_fit[col].ffill().bfill().fillna(0)

    m.fit(data_fit)

    # --- Future dataframe ---
    future = m.make_future_dataframe(periods=future_days)

    if "cap" in data.columns:
        future["cap"] = data["cap"].iloc[-1]
    if "floor" in data.columns:
        future["floor"] = data["floor"].iloc[-1]

    # Extend regressors into future
    for reg_list in [regressors_scaled, tech_scaled, pattern_regs]:
        for reg in reg_list:
            if reg in data_fit.columns:
                last_val = float(data_fit[reg].iloc[-1])
                future[reg] = future["ds"].apply(
                    lambda x, r=reg, lv=last_val: (
                        float(data_fit[data_fit["ds"] <= x][r].iloc[-1])
                        if not data_fit[data_fit["ds"] <= x].empty
                        else lv
                    )
                )
                future[reg] = future[reg].fillna(0)

    forecast = m.predict(future)

    # --- Feature contributions ---
    contributions = {}
    for reg in regressors_scaled + tech_scaled + pattern_regs:
        if reg in forecast.columns:
            base = reg.replace("_scaled", "").replace("ti_", "")
            val = forecast[reg].tail(future_days).mean()
            contributions[base] = 0.0 if pd.isna(val) else float(val)

    return m, forecast, contributions


def evaluate_holdout(
    prophet_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    holdout_days: int = 15,
) -> dict:
    """
    Evaluate forecast against actuals on the last holdout_days.

    Returns dict with mae, rmse, mape, smape, directional_accuracy, merged_df.
    """
    merged = pd.merge(
        forecast_df[["ds", "yhat"]],
        prophet_df[["ds", "y"]],
        on="ds", how="inner",
    ).sort_values("ds")

    if merged.empty:
        return _empty_metrics()

    holdout = merged.tail(holdout_days).copy() if holdout_days > 0 else merged.copy()
    if holdout.empty:
        return _empty_metrics()

    y, yhat = holdout["y"].values, holdout["yhat"].values

    mae = float(mean_absolute_error(y, yhat))
    rmse = float(np.sqrt(mean_squared_error(y, yhat)))

    # MAPE (skip zeros)
    y_nz = np.where(y == 0, np.nan, y)
    mape = float(np.nanmean(np.abs((y - yhat) / y_nz)) * 100)

    # sMAPE
    denom = (np.abs(y) + np.abs(yhat)) / 2
    denom = np.where(denom == 0, np.nan, denom)
    smape = float(np.nanmean(np.abs(y - yhat) / denom) * 100)

    # Directional accuracy
    if len(y) > 1:
        actual_dir = np.sign(np.diff(y))
        pred_dir = np.sign(np.diff(yhat))
        dir_acc = float(np.mean(actual_dir == pred_dir) * 100)
    else:
        dir_acc = np.nan

    return {
        "mae": mae,
        "rmse": rmse,
        "mape": mape,
        "smape": smape,
        "directional_accuracy": dir_acc,
        "holdout_days": len(holdout),
        "merged_df": merged,
    }


def evaluate_oos(
    full_df: pd.DataFrame,
    holdout_days: int,
    model_kwargs: dict,
    use_options: bool = False,
    growth_mode: str = "linear",
    normalize_logistic: bool = False,
    n_folds: int = 1,
) -> dict:
    """
    True out-of-sample evaluation with rolling folds.
    Trains ONLY on data before the holdout window.

    Returns: dict with mean/std metrics across folds.
    """
    if full_df is None or full_df.empty or holdout_days <= 0:
        return _empty_metrics()

    df = full_df.sort_values("ds").reset_index(drop=True).copy()
    min_train = max(60, holdout_days * 3)

    fold_metrics = []

    for fold in range(max(1, n_folds)):
        split_idx = len(df) - holdout_days * (fold + 1)
        if split_idx <= min_train:
            break

        train = df.iloc[:split_idx].copy()
        test = df.iloc[split_idx:split_idx + holdout_days].copy()
        if train.empty or test.empty:
            continue

        # Handle logistic normalization
        y_min = y_range = None
        if growth_mode == "logistic" and normalize_logistic:
            y_min = float(train["y"].min())
            y_max = float(train["y"].max())
            y_range = max(y_max - y_min, 1.0)
            train["y"] = (train["y"] - y_min) / y_range
            test["y"] = (test["y"] - y_min) / y_range
            train["cap"] = 1.2
            train["floor"] = 0
            test["cap"] = 1.2
            test["floor"] = 0

        try:
            m, forecast, _ = fit_and_forecast(
                train, future_days=holdout_days,
                use_options=use_options, **model_kwargs,
            )

            # Get predictions for test dates
            pred_df = pd.concat([train, test], ignore_index=True)
            pred_ready = pred_df.iloc[2:].copy()
            for col in pred_ready.columns:
                if col not in ("ds",):
                    pred_ready[col] = pred_ready[col].ffill().bfill().fillna(0)

            forecast_full = m.predict(pred_ready)

            # De-normalize
            if growth_mode == "logistic" and normalize_logistic and y_range:
                forecast_full["yhat"] = forecast_full["yhat"] * y_range + y_min
                pred_ready["y"] = pred_ready["y"] * y_range + y_min

            metrics = evaluate_holdout(pred_ready, forecast_full, holdout_days)
            if not np.isnan(metrics["mape"]):
                fold_metrics.append(metrics)

        except Exception as e:
            logger.debug(f"Fold {fold} failed: {e}")
            continue

    if not fold_metrics:
        return _empty_metrics()

    return {
        "mae_mean": float(np.mean([m["mae"] for m in fold_metrics])),
        "rmse_mean": float(np.mean([m["rmse"] for m in fold_metrics])),
        "mape_mean": float(np.mean([m["mape"] for m in fold_metrics])),
        "mape_std": float(np.std([m["mape"] for m in fold_metrics])) if len(fold_metrics) > 1 else 0.0,
        "smape_mean": float(np.mean([m["smape"] for m in fold_metrics])),
        "directional_accuracy_mean": float(np.nanmean([m["directional_accuracy"] for m in fold_metrics])),
        "n_folds": len(fold_metrics),
        "stability_score": float(np.mean([m["mape"] for m in fold_metrics]) +
                                  0.25 * np.std([m["mape"] for m in fold_metrics])),
    }


def _empty_metrics() -> dict:
    return {
        "mae": np.nan, "rmse": np.nan, "mape": np.nan,
        "smape": np.nan, "directional_accuracy": np.nan,
        "holdout_days": 0, "merged_df": pd.DataFrame(),
    }
