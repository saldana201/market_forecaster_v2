"""Historical Options Intelligence.

This module validates whether REAL observed Options Flow v2 snapshots carry
out-of-sample information about future returns. It never fabricates historical
options observations and it does not alter production routing by itself.

Evaluation protocol:
- One snapshot per US market session (latest observed snapshot wins).
- A snapshot is aligned to the NEXT market session open. This prevents an
  intraday snapshot from accidentally using that same day's final close.
- h-session target = next-session open -> close of the h-th session.
- Expanding walk-forward folds use an embargo of at least h snapshot rows.
- A zero-return forecast is the mandatory baseline.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

DEFAULT_HORIZONS = (1, 5, 10, 20)
MIN_UNIQUE_SESSIONS = 60

FEATURE_COLUMNS = (
    "options_signal_score",
    "directional_pressure_score",
    "pressure_coverage",
    "gamma_balance_score",
    "atm_iv",
    "skew_25d",
    "iv_term_structure_slope",
    "put_call_volume_ratio",
    "put_call_oi_ratio",
    "front_pressure_score",
    "front_skew_25d",
    "front_gamma_balance",
    "near_pressure_score",
    "near_skew_25d",
    "near_gamma_balance",
)


def _finite(value, default=np.nan) -> float:
    try:
        v = float(value)
    except Exception:
        return float(default)
    return v if np.isfinite(v) else float(default)


def _market_session_date(timestamp) -> pd.Timestamp:
    ts = pd.to_datetime(timestamp, errors="coerce", utc=True)
    if pd.isna(ts):
        return pd.NaT
    return ts.tz_convert("America/New_York").tz_localize(None).normalize()


def _bucket_map(snapshot: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for bucket in snapshot.get("maturity_buckets", []) or []:
        name = str(bucket.get("bucket", ""))
        if name:
            out[name] = bucket
    return out


def _bucket_gamma_balance(bucket: dict | None) -> float:
    if not bucket:
        return np.nan
    signed = _finite(bucket.get("signed_gamma_proxy"))
    call = abs(_finite(bucket.get("call_gamma_dollar_1pct"), 0.0))
    put = abs(_finite(bucket.get("put_gamma_dollar_1pct"), 0.0))
    denom = call + put
    return float(np.clip(signed / denom, -1, 1)) if denom > 0 else 0.0


def flatten_options_history(history: Iterable[dict]) -> pd.DataFrame:
    """Flatten persisted snapshots into one row per market session.

    Multiple genuine snapshots on the same session are deduplicated by keeping
    the latest observation. Repeated app runs cannot manufacture more sessions.
    """
    rows: list[dict] = []
    for snap in history or []:
        if not isinstance(snap, dict) or not snap.get("available"):
            continue
        ts = pd.to_datetime(snap.get("as_of_utc"), errors="coerce", utc=True)
        session_date = _market_session_date(snap.get("as_of_utc"))
        if pd.isna(ts) or pd.isna(session_date):
            continue
        buckets = _bucket_map(snap)
        front = buckets.get("0-7d", {})
        near = buckets.get("8-30d", {})
        rows.append({
            "ticker": str(snap.get("ticker", "")).upper(),
            "as_of_utc": ts,
            "session_date": session_date,
            "spot": _finite(snap.get("spot")),
            "options_signal_score": _finite(snap.get("options_signal_score")),
            "directional_pressure_score": _finite(snap.get("directional_pressure_score")),
            "pressure_coverage": _finite(snap.get("pressure_coverage")),
            "gamma_balance_score": _finite(snap.get("gamma_balance_score")),
            "atm_iv": _finite(snap.get("atm_iv")),
            "skew_25d": _finite(snap.get("skew_25d")),
            "iv_term_structure_slope": _finite(snap.get("iv_term_structure_slope")),
            "put_call_volume_ratio": _finite(snap.get("put_call_volume_ratio")),
            "put_call_oi_ratio": _finite(snap.get("put_call_oi_ratio")),
            "front_pressure_score": _finite(front.get("directional_pressure_score")),
            "front_skew_25d": _finite(front.get("skew_25d")),
            "front_gamma_balance": _bucket_gamma_balance(front),
            "near_pressure_score": _finite(near.get("directional_pressure_score")),
            "near_skew_25d": _finite(near.get("skew_25d")),
            "near_gamma_balance": _bucket_gamma_balance(near),
        })
    if not rows:
        return pd.DataFrame(columns=["ticker", "as_of_utc", "session_date", *FEATURE_COLUMNS])
    frame = pd.DataFrame(rows).sort_values("as_of_utc")
    frame = frame.drop_duplicates(subset=["session_date"], keep="last")
    return frame.sort_values("session_date").reset_index(drop=True)


def _price_frame(stock_df: pd.DataFrame) -> pd.DataFrame:
    if stock_df is None or stock_df.empty:
        raise ValueError("Historical options validation requires market data")
    if "Date" not in stock_df.columns:
        raise ValueError("Market data requires Date")
    if "Open" not in stock_df.columns or "Close" not in stock_df.columns:
        raise ValueError("Market data requires Open and Close")
    dates = pd.to_datetime(stock_df["Date"], errors="coerce")
    try:
        dates = dates.dt.tz_localize(None)
    except TypeError:
        pass
    frame = pd.DataFrame({
        "Date": dates.dt.normalize(),
        "Open": pd.to_numeric(stock_df["Open"], errors="coerce"),
        "Close": pd.to_numeric(stock_df["Close"], errors="coerce"),
    })
    frame = (
        frame.dropna(subset=["Date", "Open", "Close"])
        .sort_values("Date")
        .drop_duplicates("Date", keep="last")
        .reset_index(drop=True)
    )
    if frame.empty:
        raise ValueError("No usable market rows")
    return frame


def align_options_with_market(
    snapshots: pd.DataFrame,
    stock_df: pd.DataFrame,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
) -> pd.DataFrame:
    """Align each snapshot to a strictly later, tradable market-session open."""
    if snapshots is None or snapshots.empty:
        return pd.DataFrame()
    prices = _price_frame(stock_df)
    price_dates = prices["Date"].to_numpy(dtype="datetime64[ns]")
    aligned_rows: list[dict] = []
    horizons = tuple(sorted({max(1, int(h)) for h in horizons}))

    for _, snap in snapshots.sort_values("session_date").iterrows():
        snap_date = pd.Timestamp(snap["session_date"]).normalize()
        entry_idx = int(np.searchsorted(price_dates, np.datetime64(snap_date), side="right"))
        if entry_idx >= len(prices):
            continue
        entry_open = float(prices.iloc[entry_idx]["Open"])
        if not np.isfinite(entry_open) or entry_open <= 0:
            continue
        row = snap.to_dict()
        row["entry_date"] = pd.Timestamp(prices.iloc[entry_idx]["Date"])
        row["entry_open"] = entry_open
        for h in horizons:
            exit_idx = entry_idx + h - 1
            if exit_idx < len(prices):
                exit_close = float(prices.iloc[exit_idx]["Close"])
                row[f"target_return_{h}"] = exit_close / entry_open - 1.0
                row[f"target_exit_date_{h}"] = pd.Timestamp(prices.iloc[exit_idx]["Date"])
            else:
                row[f"target_return_{h}"] = np.nan
                row[f"target_exit_date_{h}"] = pd.NaT
        aligned_rows.append(row)
    if not aligned_rows:
        return pd.DataFrame()
    return pd.DataFrame(aligned_rows).sort_values("session_date").reset_index(drop=True)


def _walk_forward_splits(
    n_rows: int,
    horizon: int,
    *,
    n_folds: int = 3,
    min_train: int = 30,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Expanding-window splits with a horizon-sized embargo."""
    n_rows = int(n_rows)
    horizon = max(1, int(horizon))
    n_folds = max(1, int(n_folds))
    min_train = max(10, int(min_train))
    if n_rows < min_train + horizon + 5:
        return []
    test_size = max(5, min(15, n_rows // (n_folds + 2)))
    first_test = n_rows - n_folds * test_size
    splits: list[tuple[np.ndarray, np.ndarray]] = []
    for fold in range(n_folds):
        test_start = first_test + fold * test_size
        test_end = min(n_rows, test_start + test_size)
        train_end = test_start - horizon
        if train_end < min_train or test_end <= test_start:
            continue
        splits.append((np.arange(0, train_end, dtype=int), np.arange(test_start, test_end, dtype=int)))
    return splits


def _safe_mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    if len(y_true) == 0:
        return np.nan
    return float(np.mean(np.abs(np.asarray(y_true, dtype=float) - np.asarray(y_pred, dtype=float))))


def _directional_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    mask = np.isfinite(y) & np.isfinite(p) & (np.abs(y) > 1e-12)
    if not mask.any():
        return np.nan
    return float(np.mean(np.sign(y[mask]) == np.sign(p[mask])) * 100.0)


def _feature_ic(frame: pd.DataFrame, target_col: str) -> list[dict]:
    """Descriptive full-sample rank IC; never used by the production gate."""
    rows: list[dict] = []
    for feature in FEATURE_COLUMNS:
        if feature not in frame.columns:
            continue
        pair = frame[[feature, target_col]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(pair) < 10 or pair[feature].nunique() < 3:
            continue
        ic = pair[feature].corr(pair[target_col], method="spearman")
        if pd.notna(ic):
            rows.append({"feature": feature, "spearman_ic": float(ic), "abs_ic": float(abs(ic)), "samples": int(len(pair))})
    return sorted(rows, key=lambda r: r["abs_ic"], reverse=True)


def _evaluate_horizon(aligned: pd.DataFrame, horizon: int, *, n_folds: int, min_train: int) -> dict:
    target_col = f"target_return_{horizon}"
    feature_cols = [c for c in FEATURE_COLUMNS if c in aligned.columns]
    work = aligned[[*feature_cols, target_col]].copy().replace([np.inf, -np.inf], np.nan)
    work = work.dropna(subset=[target_col]).reset_index(drop=True)
    splits = _walk_forward_splits(len(work), horizon, n_folds=n_folds, min_train=min_train)
    if not splits:
        return {
            "horizon": int(horizon), "samples": int(len(work)), "folds": 0,
            "model_mae": None, "baseline_mae": None, "improvement_pct": None,
            "directional_accuracy": None, "fold_win_rate": None, "gate": "HOLD",
            "reason": "Insufficient history for embargoed walk-forward validation",
            "feature_ic": _feature_ic(work, target_col),
        }

    y_all: list[float] = []
    p_all: list[float] = []
    base_all: list[float] = []
    fold_rows: list[dict] = []
    for fold_id, (train_idx, test_idx) in enumerate(splits, start=1):
        X_train = work.iloc[train_idx][feature_cols]
        y_train = work.iloc[train_idx][target_col].to_numpy(dtype=float)
        X_test = work.iloc[test_idx][feature_cols]
        y_test = work.iloc[test_idx][target_col].to_numpy(dtype=float)
        model = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("ridge", Ridge(alpha=5.0)),
        ])
        model.fit(X_train, y_train)
        pred = np.asarray(model.predict(X_test), dtype=float)
        baseline = np.zeros_like(y_test)
        model_mae = _safe_mae(y_test, pred)
        baseline_mae = _safe_mae(y_test, baseline)
        fold_rows.append({
            "fold": fold_id, "train_rows": int(len(train_idx)), "test_rows": int(len(test_idx)),
            "model_mae": model_mae, "baseline_mae": baseline_mae,
            "beat_baseline": bool(model_mae < baseline_mae),
        })
        y_all.extend(y_test.tolist())
        p_all.extend(pred.tolist())
        base_all.extend(baseline.tolist())

    y_arr = np.asarray(y_all, dtype=float)
    p_arr = np.asarray(p_all, dtype=float)
    b_arr = np.asarray(base_all, dtype=float)
    model_mae = _safe_mae(y_arr, p_arr)
    baseline_mae = _safe_mae(y_arr, b_arr)
    improvement = ((baseline_mae - model_mae) / baseline_mae * 100.0) if np.isfinite(baseline_mae) and baseline_mae > 1e-12 else np.nan
    direction = _directional_accuracy(y_arr, p_arr)
    win_rate = float(np.mean([f["beat_baseline"] for f in fold_rows]))
    completed = len(fold_rows)
    gate = "PASS" if (
        completed >= 3 and np.isfinite(improvement) and improvement >= 3.0
        and np.isfinite(direction) and direction >= 52.0
        and win_rate >= 0.60 and len(y_arr) >= 15
    ) else "HOLD"
    reasons = []
    if completed < 3: reasons.append("fewer than 3 completed folds")
    if not np.isfinite(improvement) or improvement < 3.0: reasons.append("less than 3% MAE improvement vs zero-return baseline")
    if not np.isfinite(direction) or direction < 52.0: reasons.append("directional accuracy below 52%")
    if win_rate < 0.60: reasons.append("beats baseline on fewer than 60% of folds")
    if len(y_arr) < 15: reasons.append("fewer than 15 OOS predictions")
    return {
        "horizon": int(horizon), "samples": int(len(work)), "oos_predictions": int(len(y_arr)),
        "folds": int(completed), "model_mae": float(model_mae) if np.isfinite(model_mae) else None,
        "baseline_mae": float(baseline_mae) if np.isfinite(baseline_mae) else None,
        "improvement_pct": float(improvement) if np.isfinite(improvement) else None,
        "directional_accuracy": float(direction) if np.isfinite(direction) else None,
        "fold_win_rate": float(win_rate), "gate": gate,
        "reason": "All promotion conditions passed" if gate == "PASS" else "; ".join(reasons),
        "fold_metrics": fold_rows, "feature_ic": _feature_ic(work, target_col),
    }


def evaluate_options_history(
    history: Iterable[dict],
    stock_df: pd.DataFrame,
    *,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    min_unique_sessions: int = MIN_UNIQUE_SESSIONS,
    n_folds: int = 3,
    min_train: int = 30,
) -> dict:
    """Validate persisted real options snapshots against future market returns."""
    snapshots = flatten_options_history(history)
    unique_sessions = int(len(snapshots))
    min_unique_sessions = max(20, int(min_unique_sessions))
    result = {
        "status": "COLLECTING", "unique_sessions": unique_sessions,
        "required_sessions": min_unique_sessions,
        "progress_pct": float(min(100.0, unique_sessions / min_unique_sessions * 100.0)),
        "first_snapshot": None, "last_snapshot": None,
        "evaluation_protocol": "latest real snapshot per NY session; enter next market-session open; exit h-th session close; embargoed expanding walk-forward",
        "baseline": "zero cumulative return", "routing_effect": "NONE_IN_2_7",
        "horizons": [], "promotion_candidates": [],
    }
    if unique_sessions:
        result["first_snapshot"] = pd.Timestamp(snapshots["session_date"].min()).date().isoformat()
        result["last_snapshot"] = pd.Timestamp(snapshots["session_date"].max()).date().isoformat()
        tickers = snapshots["ticker"].dropna().astype(str)
        result["ticker"] = tickers.iloc[-1] if not tickers.empty else None
    else:
        result["ticker"] = None
        result["reason"] = "No persisted real Options Flow v2 snapshots yet"
        return result
    if unique_sessions < min_unique_sessions:
        result["reason"] = (
            f"Collecting real history: {unique_sessions}/{min_unique_sessions} unique market sessions. "
            "Repeated runs on the same day do not count as additional validation sessions."
        )
        return result
    aligned = align_options_with_market(snapshots, stock_df, horizons=horizons)
    if aligned.empty:
        result["reason"] = "Snapshots could not be aligned to later market sessions"
        return result
    horizon_results = [_evaluate_horizon(aligned, int(h), n_folds=n_folds, min_train=min_train) for h in horizons]
    result["horizons"] = horizon_results
    result["promotion_candidates"] = [int(row["horizon"]) for row in horizon_results if row.get("gate") == "PASS"]
    result["status"] = "READY"
    result["aligned_samples"] = int(len(aligned))
    result["reason"] = (
        "Validation complete. PASS horizons are research promotion candidates only; "
        "2.7 does not alter routing or Production Consensus."
    )
    return result
