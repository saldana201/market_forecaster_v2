"""Forecast Calibration + Decision Layer (v3.3).

The decision layer is downstream of deployment governance. It never changes
model weights, routing, or the approved/effective champion.

Probability calibration:
- >=20 resolved outcomes across >=5 distinct market snapshots: CALIBRATED
- 8-19 outcomes: LOW_SAMPLE, empirical probability shrunk toward 50%
- <8 outcomes: PROVISIONAL, no numeric calibrated probability is emitted

Current probability-up is estimated from the historical residual distribution:
    residual = realized_return - predicted_return
    P(up | current forecast) = P(residual > -current_predicted_return)

A Beta(1,1) smoothing prior is used before low-sample shrinkage.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from market_forecaster.core.forecast_audit import load_audit_outcomes, load_audit_runs

DECISION_HORIZONS = (1, 5, 10, 20)


@dataclass(frozen=True)
class HorizonDecision:
    horizon: int
    target_date: str
    evidence_status: str
    resolved_observations: int
    unique_market_snapshots: int
    raw_forecast_return_pct: float
    calibrated_expected_return_pct: float
    probability_up_pct: float | None
    empirical_mae_bps: float | None
    reference_entry: float
    forecast_target: float
    decision_target: float
    lower_bound: float | None
    upper_bound: float | None
    invalidation: float | None
    reward_risk: float | None
    opportunity_score: float
    direction: str
    recommendation: str
    actionable: bool
    notes: tuple[str, ...]

    def to_dict(self) -> dict:
        value = asdict(self)
        value["notes"] = list(self.notes)
        return value


@dataclass
class DecisionLayerResult:
    ticker: str
    effective_champion: str
    policy_status: str
    drift_status: str
    data_mode: str
    generated_at_utc: str
    primary_horizon: int | None
    primary_recommendation: str
    horizons: list[HorizonDecision]
    notes: list[str]

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "effective_champion": self.effective_champion,
            "policy_status": self.policy_status,
            "drift_status": self.drift_status,
            "data_mode": self.data_mode,
            "generated_at_utc": self.generated_at_utc,
            "primary_horizon": self.primary_horizon,
            "primary_recommendation": self.primary_recommendation,
            "horizons": [row.to_dict() for row in self.horizons],
            "notes": list(self.notes),
        }


def _store_dir(base_dir: str | Path | None = None) -> Path:
    if base_dir is not None:
        return Path(base_dir)
    override = os.getenv("MARKET_FORECASTER_DECISION_DIR")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[1] / ".local" / "decision_layer"


def _latest_run_per_market_snapshot(runs: list[dict]) -> dict[str, dict]:
    selected: dict[str, dict] = {}
    for run in runs:
        key = str(
            run.get("market_last_timestamp")
            or run.get("created_at_utc")
            or run.get("run_id")
        )
        current = selected.get(key)
        if current is None or str(run.get("created_at_utc", "")) >= str(current.get("created_at_utc", "")):
            selected[key] = run
    return selected


def _calibration_sample(
    runs: list[dict],
    outcomes: list[dict],
    candidate: str,
    horizon: int,
) -> list[dict]:
    selected = _latest_run_per_market_snapshot(runs)
    allowed_ids = {str(run.get("run_id")) for run in selected.values()}
    rows = []
    for outcome in outcomes:
        if int(outcome.get("horizon", 0) or 0) != int(horizon):
            continue
        run_id = str(outcome.get("run_id", ""))
        if run_id not in allowed_ids:
            continue
        score = (outcome.get("candidate_scores", {}) or {}).get(candidate)
        if not score:
            continue
        try:
            predicted = float(score.get("predicted_return"))
            realized = float(outcome.get("realized_return"))
        except Exception:
            continue
        if not (np.isfinite(predicted) and np.isfinite(realized)):
            continue
        rows.append({
            "run_id": run_id,
            "predicted_return": predicted,
            "realized_return": realized,
            "residual": realized - predicted,
            "absolute_return_error": abs(realized - predicted),
        })
    return rows


def _evidence_status(n: int, unique_runs: int) -> str:
    if n >= 20 and unique_runs >= 5:
        return "CALIBRATED"
    if n >= 8:
        return "LOW_SAMPLE"
    return "PROVISIONAL"


def _calibrated_metrics(sample: list[dict], current_predicted_return: float) -> dict:
    n = len(sample)
    unique_runs = len({row["run_id"] for row in sample})
    status = _evidence_status(n, unique_runs)

    if not sample:
        return {
            "status": status,
            "n": 0,
            "unique_runs": 0,
            "probability_up": None,
            "bias_adjustment": 0.0,
            "mae": None,
        }

    residuals = np.asarray([row["residual"] for row in sample], dtype=float)
    errors = np.asarray([row["absolute_return_error"] for row in sample], dtype=float)
    successes = int(np.sum(residuals > -float(current_predicted_return)))
    empirical_smoothed = (successes + 1.0) / (n + 2.0)

    probability = None
    if status == "CALIBRATED":
        probability = empirical_smoothed
    elif status == "LOW_SAMPLE":
        reliability = min(1.0, n / 20.0)
        probability = 0.5 + (empirical_smoothed - 0.5) * reliability

    bias_reliability = min(1.0, n / 20.0)
    bias_adjustment = float(np.median(residuals) * bias_reliability)

    return {
        "status": status,
        "n": n,
        "unique_runs": unique_runs,
        "probability_up": probability,
        "bias_adjustment": bias_adjustment,
        "mae": float(np.mean(errors)) if len(errors) else None,
    }


def _last_close(stock_df: pd.DataFrame | None) -> float:
    if stock_df is None or getattr(stock_df, "empty", True) or "Close" not in stock_df.columns:
        return 0.0
    close = stock_df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    values = pd.to_numeric(close, errors="coerce").dropna()
    return float(values.iloc[-1]) if not values.empty else 0.0


def _array(values: Any, n: int) -> np.ndarray:
    arr = np.asarray(values if values is not None else [], dtype=float)
    if len(arr) != n:
        return np.full(n, np.nan)
    return arr


def _risk_adjusted_score(
    expected_return: float,
    lower_return: float | None,
    upper_return: float | None,
    probability_up: float | None,
    evidence_n: int,
    reward_risk: float | None,
    *,
    evidence_status: str,
    cached_data: bool,
    degraded_data: bool,
    drift_status: str,
) -> float:
    if lower_return is not None and upper_return is not None:
        half_width = max((upper_return - lower_return) / 2.0, 0.005)
    else:
        half_width = max(abs(expected_return), 0.02)

    forecast_edge = min(1.0, abs(expected_return) / half_width)
    probability_edge = 0.0 if probability_up is None else min(1.0, 2.0 * abs(probability_up - 0.5))
    evidence_score = min(1.0, evidence_n / 40.0)
    rr_score = 0.0 if reward_risk is None else min(1.0, max(0.0, reward_risk) / 3.0)

    score = 100.0 * (
        0.35 * forecast_edge
        + 0.25 * probability_edge
        + 0.20 * evidence_score
        + 0.20 * rr_score
    )

    if evidence_status == "PROVISIONAL":
        score = min(score, 25.0)
    elif evidence_status == "LOW_SAMPLE":
        score = min(score, 45.0)
    if cached_data:
        score = min(score, 20.0)
    elif degraded_data:
        score = min(score, 55.0)
    if str(drift_status).upper() in {"FROZEN", "DEGRADED"}:
        score = min(score, 20.0)
    elif str(drift_status).upper() == "WATCH":
        score = min(score, 60.0)
    return float(np.clip(score, 0.0, 100.0))


def build_decision_layer(
    ticker: str,
    deployment: Any,
    stock_df: pd.DataFrame,
    *,
    runs: list[dict] | None = None,
    outcomes: list[dict] | None = None,
    base_dir: str | Path | None = None,
    horizons: Iterable[int] = DECISION_HORIZONS,
) -> DecisionLayerResult:
    symbol = str(ticker or "").upper().strip()
    if deployment is None:
        raise ValueError("Decision layer requires the governed deployment decision")

    dates = pd.DatetimeIndex(pd.to_datetime(getattr(deployment, "dates", [])))
    path = np.asarray(getattr(deployment, "path", []), dtype=float)
    if len(dates) == 0 or len(path) != len(dates):
        raise ValueError("Deployment path is unavailable or misaligned")

    lower = _array(getattr(deployment, "lower", None), len(path))
    upper = _array(getattr(deployment, "upper", None), len(path))
    spot = _last_close(stock_df)
    if not np.isfinite(spot) or spot <= 0:
        raise ValueError("Current market price is unavailable")

    candidate = str(getattr(deployment, "effective_champion", "adaptive_production_consensus"))
    policy_status = str(getattr(deployment, "policy_status", "UNKNOWN"))
    drift_status = str(getattr(deployment, "drift_status", "COLLECTING"))

    if runs is None:
        runs = load_audit_runs(symbol, base_dir=base_dir)
    if outcomes is None:
        outcomes = load_audit_outcomes(symbol, base_dir=base_dir)

    cached_data = bool(getattr(stock_df, "attrs", {}).get("is_cached", False))
    degraded_data = bool(getattr(stock_df, "attrs", {}).get("degraded_data", False))
    failover = bool(getattr(stock_df, "attrs", {}).get("provider_failover_used", False))
    data_mode = "CACHE_FALLBACK" if cached_data else ("LIVE_FALLBACK" if failover else "LIVE_PRIMARY")

    rows: list[HorizonDecision] = []
    for horizon in sorted({int(h) for h in horizons if int(h) >= 1}):
        if horizon > len(path):
            continue

        idx = horizon - 1
        target_date = pd.Timestamp(dates[idx]).isoformat()
        forecast_target = float(path[idx])
        raw_return = forecast_target / spot - 1.0

        sample = _calibration_sample(runs, outcomes, candidate, horizon)
        calibration = _calibrated_metrics(sample, raw_return)
        expected_return = raw_return + calibration["bias_adjustment"]
        decision_target = float(spot * (1.0 + expected_return))
        probability_up = calibration["probability_up"]

        lo = float(lower[idx]) if np.isfinite(lower[idx]) and lower[idx] > 0 else None
        hi = float(upper[idx]) if np.isfinite(upper[idx]) and upper[idx] > 0 else None
        lower_return = None if lo is None else lo / spot - 1.0
        upper_return = None if hi is None else hi / spot - 1.0

        direction = "BULLISH" if expected_return > 0.0025 else ("BEARISH" if expected_return < -0.0025 else "NEUTRAL")

        invalidation = None
        reward_risk = None
        notes: list[str] = []
        if direction == "BULLISH" and lo is not None and lo < spot:
            invalidation = lo
            risk = spot - lo
            reward = max(0.0, decision_target - spot)
            reward_risk = reward / risk if risk > 0 else None
        elif direction == "BEARISH" and hi is not None and hi > spot:
            invalidation = hi
            risk = hi - spot
            reward = max(0.0, spot - decision_target)
            reward_risk = reward / risk if risk > 0 else None
        else:
            notes.append("No valid interval-side invalidation level is available.")

        score = _risk_adjusted_score(
            expected_return,
            lower_return,
            upper_return,
            probability_up,
            calibration["n"],
            reward_risk,
            evidence_status=calibration["status"],
            cached_data=cached_data,
            degraded_data=degraded_data,
            drift_status=drift_status,
        )

        actionable = False
        recommendation = "WAIT"
        if calibration["status"] == "PROVISIONAL":
            recommendation = "RESEARCH_BULLISH" if direction == "BULLISH" else (
                "RESEARCH_BEARISH" if direction == "BEARISH" else "WAIT"
            )
            notes.append("Fewer than 8 resolved outcomes: no calibrated probability is emitted.")
        elif calibration["status"] == "LOW_SAMPLE":
            recommendation = "RESEARCH_BULLISH" if direction == "BULLISH" else (
                "RESEARCH_BEARISH" if direction == "BEARISH" else "WAIT"
            )
            notes.append("Probability is low-sample and shrunk toward 50%; research-only.")
        else:
            if cached_data:
                recommendation = "WAIT"
                notes.append("Cached market data blocks an actionable decision.")
            elif str(drift_status).upper() in {"FROZEN", "DEGRADED"}:
                recommendation = "WAIT"
                notes.append("Deployment drift state blocks an actionable decision.")
            elif invalidation is None or reward_risk is None:
                recommendation = "WAIT"
            elif (
                direction == "BULLISH"
                and probability_up is not None
                and probability_up >= 0.58
                and expected_return >= 0.01
                and reward_risk >= 1.5
                and score >= 55.0
            ):
                recommendation = "LONG_SETUP"
                actionable = True
            elif (
                direction == "BEARISH"
                and probability_up is not None
                and probability_up <= 0.42
                and expected_return <= -0.01
                and reward_risk >= 1.5
                and score >= 55.0
            ):
                recommendation = "SHORT_SETUP"
                actionable = True
            else:
                recommendation = "WAIT"

        if degraded_data and not cached_data:
            notes.append("Live fallback/degraded market data caps the opportunity score.")
        if str(drift_status).upper() == "WATCH":
            notes.append("Deployment drift is WATCH; opportunity score is capped.")

        rows.append(HorizonDecision(
            horizon=horizon,
            target_date=target_date,
            evidence_status=calibration["status"],
            resolved_observations=calibration["n"],
            unique_market_snapshots=calibration["unique_runs"],
            raw_forecast_return_pct=float(raw_return * 100.0),
            calibrated_expected_return_pct=float(expected_return * 100.0),
            probability_up_pct=None if probability_up is None else float(probability_up * 100.0),
            empirical_mae_bps=None if calibration["mae"] is None else float(calibration["mae"] * 10000.0),
            reference_entry=float(spot),
            forecast_target=forecast_target,
            decision_target=decision_target,
            lower_bound=lo,
            upper_bound=hi,
            invalidation=invalidation,
            reward_risk=None if reward_risk is None else float(reward_risk),
            opportunity_score=score,
            direction=direction,
            recommendation=recommendation,
            actionable=actionable,
            notes=tuple(notes),
        ))

    primary = None
    if rows:
        actionable_rows = [row for row in rows if row.actionable]
        primary = max(actionable_rows or rows, key=lambda row: row.opportunity_score)

    notes = [
        "The decision layer is downstream of deployment governance and cannot change the production champion.",
        "Probability-up is empirical residual calibration, not a guarantee of future direction.",
        "Reference entry is the current observed close; target and invalidation come from the governed path and its interval.",
    ]
    if cached_data:
        notes.append("Current market data is cached; actionable setup generation is disabled.")
    elif failover:
        notes.append("A validated live fallback provider is active; scores are conservatively capped.")

    return DecisionLayerResult(
        ticker=symbol,
        effective_champion=candidate,
        policy_status=policy_status,
        drift_status=drift_status,
        data_mode=data_mode,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        primary_horizon=None if primary is None else primary.horizon,
        primary_recommendation="UNAVAILABLE" if primary is None else primary.recommendation,
        horizons=rows,
        notes=notes,
    )


def persist_decision_snapshot(result: DecisionLayerResult, *, base_dir: str | Path | None = None) -> Path:
    root = _store_dir(base_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{result.ticker}.json"
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)
    return path


def load_decision_snapshot(ticker: str, *, base_dir: str | Path | None = None) -> dict:
    path = _store_dir(base_dir) / f"{str(ticker).upper().strip()}.json"
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}
