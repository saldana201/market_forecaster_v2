"""Market regime classification and validation-driven model routing.

The classifier is intentionally causal: every feature at row t uses data at or
before t. It does not use future swing confirmation, future returns, or centered
windows. Regime routing is learned from Model Zoo folds whose regime labels were
computed from the training window only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RegimeSnapshot:
    composite: str
    trend_state: str
    volatility_state: str
    realized_vol_20: float
    realized_vol_60: float
    volatility_percentile: float
    atr_pct_14: float
    return_5d: float
    return_20d: float
    drawdown_252: float
    as_of: pd.Timestamp

    def to_dict(self) -> dict:
        return {
            "composite": self.composite,
            "trend_state": self.trend_state,
            "volatility_state": self.volatility_state,
            "realized_vol_20": self.realized_vol_20,
            "realized_vol_60": self.realized_vol_60,
            "volatility_percentile": self.volatility_percentile,
            "atr_pct_14": self.atr_pct_14,
            "return_5d": self.return_5d,
            "return_20d": self.return_20d,
            "drawdown_252": self.drawdown_252,
            "as_of": self.as_of.isoformat(),
        }


@dataclass(frozen=True)
class RegimeRouting:
    weights: dict[str, float]
    source: str
    matching_folds: int
    current_regime: str
    current_volatility_state: str
    eligible_models: tuple[str, ...]
    reason: str

    @property
    def active(self) -> bool:
        return bool(self.weights)

    def to_dict(self) -> dict:
        return {
            "weights": self.weights,
            "source": self.source,
            "matching_folds": self.matching_folds,
            "current_regime": self.current_regime,
            "current_volatility_state": self.current_volatility_state,
            "eligible_models": list(self.eligible_models),
            "reason": self.reason,
            "active": self.active,
        }


def _to_series(df: pd.DataFrame, name: str) -> pd.Series:
    obj = df[name]
    if isinstance(obj, pd.DataFrame):
        obj = obj.iloc[:, 0]
    return pd.to_numeric(obj, errors="coerce")


def _price_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        raise ValueError("Regime engine requires non-empty market data")
    if "Date" not in df.columns:
        raise ValueError("Regime engine requires a Date column")
    close_name = "Close" if "Close" in df.columns else "Adj Close" if "Adj Close" in df.columns else None
    if close_name is None:
        raise ValueError("Regime engine requires Close or Adj Close")

    out = pd.DataFrame({
        "Date": pd.to_datetime(df["Date"], errors="coerce"),
        "Close": _to_series(df, close_name),
    })
    for name in ("High", "Low"):
        if name in df.columns:
            out[name] = _to_series(df, name)
    out = out.dropna(subset=["Date", "Close"]).sort_values("Date").drop_duplicates("Date", keep="last")
    return out.reset_index(drop=True)


def _rolling_percentile_last(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return np.nan
    return float(np.mean(arr <= arr[-1]))


def compute_regime_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return a causal regime feature timeline for market history."""
    frame = _price_frame(df)
    close = frame["Close"]
    log_ret = np.log(close).diff()

    frame["return_1d"] = close.pct_change()
    frame["return_5d"] = close.pct_change(5)
    frame["return_20d"] = close.pct_change(20)
    frame["realized_vol_20"] = log_ret.rolling(20, min_periods=15).std() * np.sqrt(252)
    frame["realized_vol_60"] = log_ret.rolling(60, min_periods=40).std() * np.sqrt(252)
    frame["volatility_percentile"] = frame["realized_vol_20"].rolling(
        252, min_periods=60
    ).apply(_rolling_percentile_last, raw=True)

    frame["ema_20"] = close.ewm(span=20, adjust=False, min_periods=10).mean()
    frame["ema_50"] = close.ewm(span=50, adjust=False, min_periods=20).mean()
    frame["ema_gap_pct"] = (frame["ema_20"] - frame["ema_50"]) / close.replace(0, np.nan)

    rolling_high = close.rolling(252, min_periods=20).max()
    frame["drawdown_252"] = close / rolling_high - 1.0

    if {"High", "Low"}.issubset(frame.columns):
        prev_close = close.shift(1)
        true_range = pd.concat([
            frame["High"] - frame["Low"],
            (frame["High"] - prev_close).abs(),
            (frame["Low"] - prev_close).abs(),
        ], axis=1).max(axis=1)
        frame["atr_pct_14"] = true_range.rolling(14, min_periods=10).mean() / close.replace(0, np.nan)
    else:
        frame["atr_pct_14"] = frame["return_1d"].abs().rolling(14, min_periods=10).mean()

    daily_sigma = frame["realized_vol_20"] / np.sqrt(252)
    trend_threshold = np.maximum(0.004, daily_sigma * 0.75)
    up = (frame["ema_gap_pct"] > trend_threshold) & (frame["return_20d"] > 0)
    down = (frame["ema_gap_pct"] < -trend_threshold) & (frame["return_20d"] < 0)
    frame["trend_state"] = np.select([up, down], ["UP", "DOWN"], default="RANGE")

    vp = frame["volatility_percentile"]
    frame["volatility_state"] = np.select(
        [vp >= 0.90, vp >= 0.75, vp <= 0.25],
        ["EXTREME", "HIGH", "LOW"],
        default="NORMAL",
    )

    # Stress requires both unusually elevated volatility and material downside.
    # Thresholds are scale-aware through realized volatility as well as absolute
    # drawdown/return safeguards.
    sigma5 = daily_sigma * np.sqrt(5)
    stress = (
        (vp >= 0.85)
        & (
            (frame["return_5d"] <= -np.maximum(0.04, 1.75 * sigma5))
            | (frame["drawdown_252"] <= -np.maximum(0.10, 3.0 * daily_sigma))
        )
    )
    high_vol = frame["volatility_state"].isin(["HIGH", "EXTREME"])
    frame["composite_regime"] = np.select(
        [stress, high_vol, frame["trend_state"].eq("UP"), frame["trend_state"].eq("DOWN")],
        ["STRESS", "HIGH_VOL", "TREND_UP", "TREND_DOWN"],
        default="RANGE",
    )
    return frame


def classify_regime(df: pd.DataFrame) -> RegimeSnapshot:
    features = compute_regime_features(df)
    valid = features.dropna(subset=["realized_vol_20"])
    if valid.empty:
        raise ValueError("Not enough history to classify regime; need roughly 20+ observations")
    row = valid.iloc[-1]

    def f(name: str, default: float = np.nan) -> float:
        value = row.get(name, default)
        return float(value) if pd.notna(value) else float(default)

    return RegimeSnapshot(
        composite=str(row["composite_regime"]),
        trend_state=str(row["trend_state"]),
        volatility_state=str(row["volatility_state"]),
        realized_vol_20=f("realized_vol_20"),
        realized_vol_60=f("realized_vol_60"),
        volatility_percentile=f("volatility_percentile", 0.5),
        atr_pct_14=f("atr_pct_14"),
        return_5d=f("return_5d"),
        return_20d=f("return_20d"),
        drawdown_252=f("drawdown_252"),
        as_of=pd.Timestamp(row["Date"]),
    )


def _inverse_error_weights(errors: pd.Series) -> dict[str, float]:
    clean = errors.replace([np.inf, -np.inf], np.nan).dropna()
    clean = clean[clean >= 0]
    if clean.empty:
        return {}
    raw = 1.0 / clean.clip(lower=0.25)
    total = float(raw.sum())
    if total <= 0:
        return {}
    return {str(k): float(v / total) for k, v in raw.items()}


def derive_regime_routing(
    folds: pd.DataFrame,
    leaderboard: pd.DataFrame,
    current: RegimeSnapshot,
    *,
    min_matching_folds: int = 2,
    ensemble_models: Iterable[str] = ("arima", "ridge", "random_forest"),
) -> RegimeRouting:
    """Learn ensemble priors from validation folds matching the current regime.

    Only globally production-gated models are eligible. Exact composite-regime
    evidence is preferred; volatility-state evidence is a conservative fallback.
    If there is insufficient matching evidence, no routing weights are returned.
    """
    if folds is None or folds.empty or leaderboard is None or leaderboard.empty:
        return RegimeRouting({}, "none", 0, current.composite, current.volatility_state, (), "No validation evidence available")

    allowed = set(ensemble_models)
    gated = leaderboard[
        (leaderboard.get("production_gate") == "PASS")
        & leaderboard["model"].isin(allowed)
    ]["model"].astype(str).tolist()
    if not gated:
        return RegimeRouting({}, "none", 0, current.composite, current.volatility_state, (), "No ensemble model has passed the global production gate")

    candidates = folds[folds["model"].isin(gated)].copy()
    if candidates.empty:
        return RegimeRouting({}, "none", 0, current.composite, current.volatility_state, tuple(gated), "No gated model has fold evidence")

    def _route_for(mask: pd.Series, source: str) -> Optional[RegimeRouting]:
        subset = candidates[mask].copy()
        matching_fold_count = int(subset["fold"].nunique()) if not subset.empty else 0
        if matching_fold_count < min_matching_folds:
            return None
        by_model = subset.groupby("model")["smape"].mean()
        # Require every weighted model to have at least min_matching_folds rows.
        counts = subset.groupby("model")["fold"].nunique()
        by_model = by_model[counts.reindex(by_model.index).fillna(0) >= min_matching_folds]
        weights = _inverse_error_weights(by_model)
        if not weights:
            return None
        return RegimeRouting(
            weights=weights,
            source=source,
            matching_folds=matching_fold_count,
            current_regime=current.composite,
            current_volatility_state=current.volatility_state,
            eligible_models=tuple(sorted(weights)),
            reason=f"Learned from {matching_fold_count} validation folds matching {source}",
        )

    if "regime" in candidates.columns:
        exact = _route_for(candidates["regime"].eq(current.composite), "composite_regime")
        if exact:
            return exact
    if "volatility_state" in candidates.columns:
        vol = _route_for(candidates["volatility_state"].eq(current.volatility_state), "volatility_state")
        if vol:
            return vol

    return RegimeRouting(
        {}, "none", 0, current.composite, current.volatility_state, tuple(gated),
        f"Fewer than {min_matching_folds} matching validation folds; routing remains disabled",
    )


def ensemble_weight_names(weights: dict[str, float]) -> dict[str, float]:
    """Translate Model Zoo names to EnsembleForecaster names."""
    mapping = {"random_forest": "rf", "ridge": "ridge", "arima": "arima", "lstm": "lstm"}
    translated = {mapping[k]: float(v) for k, v in weights.items() if k in mapping and v > 0}
    total = sum(translated.values())
    return {k: v / total for k, v in translated.items()} if total > 0 else {}
