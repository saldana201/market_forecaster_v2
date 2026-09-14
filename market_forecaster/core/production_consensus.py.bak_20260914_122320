"""Production consensus path: validated classic ensemble + gated XGBoost anchors.

Only XGBoost horizons that pass their global production gate may influence the
consensus. Regime-specific PASS evidence increases the maximum blend weight;
missing regime evidence never blocks a globally valid horizon, but keeps its
influence deliberately small.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ConsensusAnchor:
    horizon: int
    target_date: str
    ensemble_price: float
    xgb_base_price: float
    xgb_bear_price: float
    xgb_bull_price: float
    blend_weight: float
    production_gate: str
    regime_gate: str
    regime_matching_folds: int
    improvement_vs_baseline_pct: float
    directional_accuracy_pct: float
    interval_coverage_pct: float
    evidence_source: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProductionConsensusResult:
    ticker: str
    dates: pd.DatetimeIndex
    ensemble: np.ndarray
    consensus: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    anchors: list[ConsensusAnchor]
    used_horizons: list[int]
    current_regime: str
    status: str
    notes: list[str]

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "dates": [pd.Timestamp(x).isoformat() for x in self.dates],
            "ensemble": [float(x) for x in self.ensemble],
            "consensus": [float(x) for x in self.consensus],
            "lower": [None if not np.isfinite(x) else float(x) for x in self.lower],
            "upper": [None if not np.isfinite(x) else float(x) for x in self.upper],
            "anchors": [a.to_dict() for a in self.anchors],
            "used_horizons": list(self.used_horizons),
            "current_regime": self.current_regime,
            "status": self.status,
            "notes": list(self.notes),
        }


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _validation(item: Any) -> Any:
    return _get(item, "validation", {})


def _reliability_weight(validation: Any) -> tuple[float, str]:
    """Return a conservative XGB blend weight and evidence label."""
    if str(_get(validation, "production_gate", "HOLD")).upper() != "PASS":
        return 0.0, "global_hold"

    improvement = float(_get(validation, "improvement_vs_baseline_pct", np.nan))
    direction = float(_get(validation, "directional_accuracy_pct", np.nan))
    coverage = float(_get(validation, "interval_coverage_pct", np.nan))

    imp_score = float(np.clip((improvement - 2.0) / 18.0, 0.0, 1.0)) if np.isfinite(improvement) else 0.0
    dir_score = float(np.clip((direction - 50.0) / 25.0, 0.0, 1.0)) if np.isfinite(direction) else 0.0
    # 80% is the nominal target for a 10-90 interval. Reward reasonable calibration,
    # but do not overfit to exact 80% with only a few folds.
    cov_score = float(np.clip(1.0 - abs(coverage - 80.0) / 50.0, 0.0, 1.0)) if np.isfinite(coverage) else 0.0
    score = 0.50 * imp_score + 0.30 * dir_score + 0.20 * cov_score

    regime_gate = str(_get(validation, "regime_gate", "HOLD")).upper()
    matching = int(_get(validation, "regime_matching_folds", 0) or 0)
    if regime_gate == "PASS" and matching >= 2:
        # Regime-confirmed horizon: 20-35% maximum influence.
        return float(0.20 + 0.15 * score), "global_plus_regime_pass"

    # Globally valid but no matching regime evidence: only 10-15% influence.
    return float(0.10 + 0.05 * score), "global_pass_only"


def _safe_array(values: Any, length: int) -> np.ndarray:
    arr = np.asarray(values if values is not None else [], dtype=float)
    if len(arr) != length:
        return np.full(length, np.nan, dtype=float)
    return arr


def build_production_consensus(
    ensemble_result: dict,
    xgb_result: Any,
    ticker: Optional[str] = None,
) -> ProductionConsensusResult:
    """Blend gated XGBoost horizon anchors into the validated daily ensemble path.

    The adjustment is applied in log-price space and linearly interpolated between
    accepted anchor horizons. Beyond the last accepted anchor, the proportional
    adjustment is held constant rather than extrapolating a new slope.
    """
    if not ensemble_result or "ensemble" not in ensemble_result or "dates" not in ensemble_result:
        raise ValueError("Production consensus requires an existing ensemble forecast")

    base = np.asarray(ensemble_result["ensemble"], dtype=float)
    dates = pd.DatetimeIndex(pd.to_datetime(ensemble_result["dates"]))
    if len(base) == 0 or len(base) != len(dates) or not np.isfinite(base).all() or (base <= 0).any():
        raise ValueError("Ensemble path must contain positive finite prices aligned to forecast dates")

    lower = _safe_array(ensemble_result.get("lower"), len(base))
    upper = _safe_array(ensemble_result.get("upper"), len(base))

    forecasts = list(_get(xgb_result, "forecasts", []) or [])
    current_regime = str((_get(xgb_result, "config", {}) or {}).get("current_regime", "UNKNOWN"))
    resolved_ticker = str(ticker or _get(xgb_result, "ticker", "")).upper().strip()

    anchors: list[ConsensusAnchor] = []
    log_adjustments: dict[int, float] = {}

    for item in forecasts:
        horizon = int(_get(item, "horizon", 0) or 0)
        if horizon < 1 or horizon > len(base):
            continue
        validation = _validation(item)
        weight, source = _reliability_weight(validation)
        if weight <= 0:
            continue

        xgb_price = float(_get(item, "base_price", np.nan))
        bear_price = float(_get(item, "bear_price", np.nan))
        bull_price = float(_get(item, "bull_price", np.nan))
        ensemble_price = float(base[horizon - 1])
        if not np.isfinite(xgb_price) or xgb_price <= 0 or ensemble_price <= 0:
            continue

        adjustment = weight * (np.log(xgb_price) - np.log(ensemble_price))
        log_adjustments[horizon] = float(adjustment)
        anchors.append(ConsensusAnchor(
            horizon=horizon,
            target_date=str(_get(item, "target_date", dates[horizon - 1].isoformat())),
            ensemble_price=ensemble_price,
            xgb_base_price=xgb_price,
            xgb_bear_price=bear_price,
            xgb_bull_price=bull_price,
            blend_weight=weight,
            production_gate=str(_get(validation, "production_gate", "HOLD")),
            regime_gate=str(_get(validation, "regime_gate", "HOLD")),
            regime_matching_folds=int(_get(validation, "regime_matching_folds", 0) or 0),
            improvement_vs_baseline_pct=float(_get(validation, "improvement_vs_baseline_pct", np.nan)),
            directional_accuracy_pct=float(_get(validation, "directional_accuracy_pct", np.nan)),
            interval_coverage_pct=float(_get(validation, "interval_coverage_pct", np.nan)),
            evidence_source=source,
        ))

    if not anchors:
        return ProductionConsensusResult(
            ticker=resolved_ticker,
            dates=dates,
            ensemble=base.copy(),
            consensus=base.copy(),
            lower=lower.copy(),
            upper=upper.copy(),
            anchors=[],
            used_horizons=[],
            current_regime=current_regime,
            status="ENSEMBLE_ONLY",
            notes=[
                "No XGBoost horizon passed the production gate inside the ensemble forecast horizon.",
                "The validated classic ensemble remains unchanged.",
            ],
        )

    anchors.sort(key=lambda a: a.horizon)
    x_points = np.array([0] + [a.horizon for a in anchors], dtype=float)
    y_points = np.array([0.0] + [log_adjustments[a.horizon] for a in anchors], dtype=float)
    query = np.arange(1, len(base) + 1, dtype=float)
    # np.interp holds the final value after the last anchor, preventing unsupported
    # extrapolation of a new slope.
    adj = np.interp(query, x_points, y_points)
    consensus = np.exp(np.log(base) + adj)

    # Preserve the calibrated ensemble interval shape and shift it by the same
    # proportional adjustment. XGB Bear/Bull values remain visible as scenario
    # anchors in the UI; they are not mislabeled as conformal confidence bands.
    scale = consensus / base
    shifted_lower = lower * scale
    shifted_upper = upper * scale

    return ProductionConsensusResult(
        ticker=resolved_ticker,
        dates=dates,
        ensemble=base.copy(),
        consensus=consensus,
        lower=shifted_lower,
        upper=shifted_upper,
        anchors=anchors,
        used_horizons=[a.horizon for a in anchors],
        current_regime=current_regime,
        status="XGB_GATED_CONSENSUS",
        notes=[
            "Only globally PASS XGBoost horizons can influence the production consensus.",
            "Regime-confirmed PASS horizons may receive 20-35% anchor weight; global-only PASS horizons are capped at 10-15%.",
            "Daily-path adjustments are interpolated in log-price space between validated horizon anchors.",
            "The classic ensemble conformal interval is shifted with the consensus path; XGBoost Bear/Bull values remain scenario anchors, not confidence intervals.",
        ],
    )
