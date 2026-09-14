"""Adaptive promotion of historically validated Options Flow features.

v2.8 is deliberately conservative:
- Options must first pass Historical Options Intelligence (v2.7).
- The most recent OOS fold must still beat the zero-return baseline.
- Current feature coverage must be adequate.
- Promoted options anchors are capped at 5-15% influence.
- A failed/weak/stale evidence state cleanly falls back to the pre-options
  Production Consensus path.

This module does not claim true dealer GEX or true aggressor flow. It promotes
only the observed proxy features that earned out-of-sample evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from market_forecaster.core.historical_options import (
    FEATURE_COLUMNS,
    align_options_with_market,
    evaluate_options_history,
    flatten_options_history,
)


HARD_RETURN_CAPS = {
    1: 0.15,
    5: 0.25,
    10: 0.35,
    20: 0.50,
}


@dataclass(frozen=True)
class OptionsPromotionAnchor:
    horizon: int
    predicted_return: float
    target_price: float
    blend_weight: float
    feature_completeness: float
    global_gate: str
    recent_fold_gate: str
    improvement_pct: float
    directional_accuracy_pct: float
    fold_win_rate: float
    training_samples: int
    empirical_floor: float
    empirical_ceiling: float
    evidence_source: str = "historical_options_oos_pass"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OptionsPromotionResult:
    ticker: str
    as_of_utc: str
    spot: float
    status: str
    validation_status: str
    unique_sessions: int
    anchors: list[OptionsPromotionAnchor]
    promoted_horizons: list[int]
    notes: list[str]

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "as_of_utc": self.as_of_utc,
            "spot": self.spot,
            "status": self.status,
            "validation_status": self.validation_status,
            "unique_sessions": self.unique_sessions,
            "anchors": [a.to_dict() for a in self.anchors],
            "promoted_horizons": list(self.promoted_horizons),
            "notes": list(self.notes),
        }


@dataclass
class AdaptiveOptionsConsensusResult:
    ticker: str
    dates: pd.DatetimeIndex
    ensemble: np.ndarray
    base_consensus: np.ndarray
    consensus: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    xgb_anchors: list[Any]
    options_anchors: list[OptionsPromotionAnchor]
    current_regime: str
    base_status: str
    status: str
    notes: list[str]

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "dates": [pd.Timestamp(x).isoformat() for x in self.dates],
            "ensemble": [float(x) for x in self.ensemble],
            "base_consensus": [float(x) for x in self.base_consensus],
            "consensus": [float(x) for x in self.consensus],
            "lower": [None if not np.isfinite(x) else float(x) for x in self.lower],
            "upper": [None if not np.isfinite(x) else float(x) for x in self.upper],
            "xgb_anchors": [
                a.to_dict() if hasattr(a, "to_dict") else dict(a)
                for a in self.xgb_anchors
            ],
            "options_anchors": [a.to_dict() for a in self.options_anchors],
            "current_regime": self.current_regime,
            "base_status": self.base_status,
            "status": self.status,
            "notes": list(self.notes),
        }


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _finite(value, default=np.nan) -> float:
    try:
        v = float(value)
    except Exception:
        return float(default)
    return v if np.isfinite(v) else float(default)


def _current_feature_frame(snapshot: dict) -> pd.DataFrame:
    frame = flatten_options_history([snapshot])
    if frame.empty:
        return frame
    cols = [c for c in FEATURE_COLUMNS if c in frame.columns]
    return frame[cols].tail(1).copy()


def feature_completeness(snapshot: dict) -> float:
    frame = _current_feature_frame(snapshot)
    if frame.empty:
        return 0.0
    row = frame.iloc[-1]
    usable = 0
    total = 0
    for col in FEATURE_COLUMNS:
        if col not in frame.columns:
            continue
        total += 1
        value = _finite(row.get(col))
        if np.isfinite(value):
            usable += 1
    return float(usable / total) if total else 0.0


def promotion_gate_for_horizon(
    horizon_validation: dict,
    *,
    current_feature_completeness: float,
    min_feature_completeness: float = 0.60,
) -> tuple[bool, str]:
    """Return whether a v2.7 PASS is still healthy enough for production use."""
    if str(horizon_validation.get("gate", "HOLD")).upper() != "PASS":
        return False, "global_validation_hold"

    if float(current_feature_completeness) < float(min_feature_completeness):
        return False, "current_feature_coverage_hold"

    folds = horizon_validation.get("fold_metrics", []) or []
    if not folds:
        return False, "missing_recent_oos_fold"

    latest = folds[-1]
    if not bool(latest.get("beat_baseline", False)):
        return False, "latest_oos_fold_demoted"

    model_mae = _finite(latest.get("model_mae"))
    baseline_mae = _finite(latest.get("baseline_mae"))
    if not (np.isfinite(model_mae) and np.isfinite(baseline_mae) and baseline_mae > 0):
        return False, "invalid_recent_oos_metrics"
    if model_mae >= baseline_mae:
        return False, "latest_oos_fold_demoted"

    return True, "global_pass_plus_latest_oos_pass"


def promotion_weight(horizon_validation: dict) -> float:
    """Map OOS quality to a hard-capped 5-15% options anchor weight."""
    if str(horizon_validation.get("gate", "HOLD")).upper() != "PASS":
        return 0.0

    improvement = _finite(horizon_validation.get("improvement_pct"))
    direction = _finite(horizon_validation.get("directional_accuracy"))
    fold_win = _finite(horizon_validation.get("fold_win_rate"))

    imp_score = float(np.clip((improvement - 3.0) / 17.0, 0.0, 1.0)) if np.isfinite(improvement) else 0.0
    dir_score = float(np.clip((direction - 52.0) / 18.0, 0.0, 1.0)) if np.isfinite(direction) else 0.0
    win_score = float(np.clip((fold_win - 0.60) / 0.40, 0.0, 1.0)) if np.isfinite(fold_win) else 0.0
    quality = 0.50 * imp_score + 0.30 * dir_score + 0.20 * win_score
    return float(np.clip(0.05 + 0.10 * quality, 0.05, 0.15))


def _hard_cap_for_horizon(horizon: int) -> float:
    horizon = int(horizon)
    if horizon in HARD_RETURN_CAPS:
        return HARD_RETURN_CAPS[horizon]
    return float(min(0.60, 0.12 + 0.02 * np.sqrt(max(horizon, 1))))


def _fit_promoted_anchor(
    aligned: pd.DataFrame,
    current_features: pd.DataFrame,
    horizon_validation: dict,
    spot: float,
) -> OptionsPromotionAnchor | None:
    horizon = int(horizon_validation.get("horizon", 0) or 0)
    if horizon <= 0:
        return None

    target_col = f"target_return_{horizon}"
    if target_col not in aligned.columns:
        return None

    feature_cols = [c for c in FEATURE_COLUMNS if c in aligned.columns and c in current_features.columns]
    if not feature_cols:
        return None

    train = aligned[[*feature_cols, target_col]].replace([np.inf, -np.inf], np.nan)
    train = train.dropna(subset=[target_col]).reset_index(drop=True)
    if len(train) < 30:
        return None

    model = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("ridge", Ridge(alpha=5.0)),
    ])
    model.fit(train[feature_cols], train[target_col].to_numpy(dtype=float))
    raw_pred = float(model.predict(current_features[feature_cols])[0])

    target = train[target_col].to_numpy(dtype=float)
    empirical_lo = float(np.nanquantile(target, 0.025))
    empirical_hi = float(np.nanquantile(target, 0.975))
    hard = _hard_cap_for_horizon(horizon)
    lo = max(empirical_lo, -hard)
    hi = min(empirical_hi, hard)
    if lo > hi:
        lo, hi = -hard, hard
    pred = float(np.clip(raw_pred, lo, hi))

    completeness = float(current_features[feature_cols].notna().sum(axis=1).iloc[-1] / max(len(feature_cols), 1))
    weight = promotion_weight(horizon_validation)
    folds = horizon_validation.get("fold_metrics", []) or []
    latest_gate = "PASS" if folds and folds[-1].get("beat_baseline", False) else "HOLD"

    return OptionsPromotionAnchor(
        horizon=horizon,
        predicted_return=pred,
        target_price=float(spot * (1.0 + pred)),
        blend_weight=weight,
        feature_completeness=completeness,
        global_gate=str(horizon_validation.get("gate", "HOLD")),
        recent_fold_gate=latest_gate,
        improvement_pct=_finite(horizon_validation.get("improvement_pct"), 0.0),
        directional_accuracy_pct=_finite(horizon_validation.get("directional_accuracy"), 0.0),
        fold_win_rate=_finite(horizon_validation.get("fold_win_rate"), 0.0),
        training_samples=int(len(train)),
        empirical_floor=lo,
        empirical_ceiling=hi,
    )


def build_options_promotion(
    history: Iterable[dict],
    stock_df: pd.DataFrame,
    current_snapshot: dict | None,
    *,
    validation_result: Optional[dict] = None,
) -> OptionsPromotionResult:
    """Train current options anchors only for horizons still eligible for promotion."""
    current_snapshot = current_snapshot or {}
    ticker = str(current_snapshot.get("ticker", "")).upper().strip()
    as_of = str(current_snapshot.get("as_of_utc", ""))
    spot = _finite(current_snapshot.get("spot"), 0.0)

    if not current_snapshot.get("available") or spot <= 0:
        return OptionsPromotionResult(
            ticker=ticker,
            as_of_utc=as_of,
            spot=max(spot, 0.0),
            status="HOLD",
            validation_status="UNAVAILABLE",
            unique_sessions=0,
            anchors=[],
            promoted_horizons=[],
            notes=["No usable current Options Flow v2 snapshot is available."],
        )

    history_list = list(history or [])
    if validation_result is None:
        validation_result = evaluate_options_history(history_list, stock_df)

    validation_status = str(validation_result.get("status", "COLLECTING"))
    unique_sessions = int(validation_result.get("unique_sessions", 0) or 0)
    if validation_status != "READY":
        return OptionsPromotionResult(
            ticker=ticker,
            as_of_utc=as_of,
            spot=spot,
            status="COLLECTING",
            validation_status=validation_status,
            unique_sessions=unique_sessions,
            anchors=[],
            promoted_horizons=[],
            notes=[
                validation_result.get("reason", "Historical options validation is not ready."),
                "Production consensus remains unchanged until real OOS evidence is sufficient.",
            ],
        )

    current_features = _current_feature_frame(current_snapshot)
    completeness = feature_completeness(current_snapshot)
    if current_features.empty:
        return OptionsPromotionResult(
            ticker=ticker,
            as_of_utc=as_of,
            spot=spot,
            status="HOLD",
            validation_status=validation_status,
            unique_sessions=unique_sessions,
            anchors=[],
            promoted_horizons=[],
            notes=["Current options snapshot could not be converted into model features."],
        )

    flattened = flatten_options_history(history_list)
    horizons = [int(row.get("horizon", 0)) for row in validation_result.get("horizons", []) if int(row.get("horizon", 0)) > 0]
    aligned = align_options_with_market(flattened, stock_df, horizons=horizons) if horizons else pd.DataFrame()

    anchors: list[OptionsPromotionAnchor] = []
    demotions: list[str] = []
    for row in validation_result.get("horizons", []) or []:
        horizon = int(row.get("horizon", 0) or 0)
        active, reason = promotion_gate_for_horizon(
            row,
            current_feature_completeness=completeness,
        )
        if not active:
            if str(row.get("gate", "HOLD")).upper() == "PASS":
                demotions.append(f"{horizon}D: {reason}")
            continue

        anchor = _fit_promoted_anchor(aligned, current_features, row, spot)
        if anchor is not None and anchor.blend_weight > 0:
            anchors.append(anchor)

    anchors.sort(key=lambda a: a.horizon)
    if anchors:
        notes = [
            "Only v2.7 PASS horizons with a still-winning latest OOS fold are promoted.",
            "Options influence is capped at 5-15% per anchor and is applied after the classic/XGBoost production consensus.",
            "Predicted returns are clipped to empirical training ranges plus hard horizon risk caps.",
        ]
        if demotions:
            notes.append("Auto-demoted horizon(s): " + "; ".join(demotions))
        status = "ACTIVE"
    else:
        notes = [
            "No options horizon currently qualifies for production influence.",
            "The pre-options Production Consensus remains unchanged.",
        ]
        if demotions:
            notes.append("Auto-demoted horizon(s): " + "; ".join(demotions))
        status = "HOLD"

    return OptionsPromotionResult(
        ticker=ticker,
        as_of_utc=as_of,
        spot=spot,
        status=status,
        validation_status=validation_status,
        unique_sessions=unique_sessions,
        anchors=anchors,
        promoted_horizons=[a.horizon for a in anchors],
        notes=notes,
    )


def _safe_array(values: Any, length: int) -> np.ndarray:
    arr = np.asarray(values if values is not None else [], dtype=float)
    if len(arr) != length:
        return np.full(length, np.nan, dtype=float)
    return arr


def build_adaptive_options_consensus(
    base_result: Any,
    promotion: OptionsPromotionResult | dict | None,
) -> AdaptiveOptionsConsensusResult:
    """Apply promoted options return anchors on top of the existing consensus."""
    dates = pd.DatetimeIndex(pd.to_datetime(_get(base_result, "dates", [])))
    base_consensus = np.asarray(_get(base_result, "consensus", []), dtype=float)
    ensemble = np.asarray(_get(base_result, "ensemble", base_consensus), dtype=float)

    if len(dates) == 0 or len(base_consensus) != len(dates):
        raise ValueError("Adaptive options consensus requires an aligned base consensus path")
    if not np.isfinite(base_consensus).all() or (base_consensus <= 0).any():
        raise ValueError("Base consensus must contain positive finite prices")

    lower = _safe_array(_get(base_result, "lower", None), len(base_consensus))
    upper = _safe_array(_get(base_result, "upper", None), len(base_consensus))
    ticker = str(_get(base_result, "ticker", "")).upper()
    current_regime = str(_get(base_result, "current_regime", "UNKNOWN"))
    base_status = str(_get(base_result, "status", "UNKNOWN"))
    xgb_anchors = list(_get(base_result, "anchors", []) or [])

    raw_anchors = list(_get(promotion, "anchors", []) or [])
    options_anchors: list[OptionsPromotionAnchor] = []
    log_adjustments: dict[int, float] = {}

    for raw in raw_anchors:
        if isinstance(raw, OptionsPromotionAnchor):
            anchor = raw
        else:
            anchor = OptionsPromotionAnchor(**raw)

        h = int(anchor.horizon)
        if h < 1 or h > len(base_consensus):
            continue
        target = float(anchor.target_price)
        base_price = float(base_consensus[h - 1])
        weight = float(np.clip(anchor.blend_weight, 0.0, 0.15))
        if not np.isfinite(target) or target <= 0 or base_price <= 0 or weight <= 0:
            continue
        log_adjustments[h] = float(weight * (np.log(target) - np.log(base_price)))
        options_anchors.append(anchor)

    if not options_anchors:
        return AdaptiveOptionsConsensusResult(
            ticker=ticker,
            dates=dates,
            ensemble=ensemble.copy(),
            base_consensus=base_consensus.copy(),
            consensus=base_consensus.copy(),
            lower=lower.copy(),
            upper=upper.copy(),
            xgb_anchors=xgb_anchors,
            options_anchors=[],
            current_regime=current_regime,
            base_status=base_status,
            status=base_status,
            notes=[
                "No historically validated options anchor is active.",
                "The pre-options Production Consensus remains unchanged.",
            ],
        )

    options_anchors.sort(key=lambda a: a.horizon)
    x_points = np.array([0] + [a.horizon for a in options_anchors], dtype=float)
    y_points = np.array([0.0] + [log_adjustments[a.horizon] for a in options_anchors], dtype=float)
    query = np.arange(1, len(base_consensus) + 1, dtype=float)
    adj = np.interp(query, x_points, y_points)
    final_consensus = np.exp(np.log(base_consensus) + adj)

    scale = final_consensus / base_consensus
    shifted_lower = lower * scale
    shifted_upper = upper * scale

    return AdaptiveOptionsConsensusResult(
        ticker=ticker,
        dates=dates,
        ensemble=ensemble.copy(),
        base_consensus=base_consensus.copy(),
        consensus=final_consensus,
        lower=shifted_lower,
        upper=shifted_upper,
        xgb_anchors=xgb_anchors,
        options_anchors=options_anchors,
        current_regime=current_regime,
        base_status=base_status,
        status="OPTIONS_ADAPTIVE_CONSENSUS",
        notes=[
            "Historically validated options anchors are layered after the classic/XGBoost production consensus.",
            "Each options anchor is capped at 15% influence.",
            "A horizon is automatically demoted when its latest OOS fold no longer beats baseline.",
            "Options GEX and directional-flow inputs remain explicitly labeled proxy features.",
        ],
    )
