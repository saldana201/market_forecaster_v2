"""Multi-ticker opportunity ranking for Market Forecaster 3.4.

The ranking layer consumes persisted 3.3 decision snapshots. It does not run
forecast models, change deployment champions, or bypass decision-layer gates.

Ranking score:
- starts from the 3.3 opportunity score
- penalizes weak calibration evidence
- penalizes fallback/cached data
- penalizes deployment drift
- penalizes stale decision snapshots
- penalizes highly correlated same-direction opportunities

Relative risk-budget shares are research sizing caps, not trade execution.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.decision_layer import load_decision_snapshot

_TICKER_RE = re.compile(r"^[A-Z0-9.^=_-]{1,24}$")

EVIDENCE_MULTIPLIER = {
    "CALIBRATED": 1.00,
    "LOW_SAMPLE": 0.65,
    "PROVISIONAL": 0.35,
}
DATA_MULTIPLIER = {
    "LIVE_PRIMARY": 1.00,
    "LIVE_FALLBACK": 0.80,
    "CACHE_FALLBACK": 0.30,
}
DRIFT_MULTIPLIER = {
    "HEALTHY": 1.00,
    "COLLECTING": 0.85,
    "WATCH": 0.70,
    "DEGRADED": 0.25,
    "FROZEN": 0.25,
}
RECOMMENDATION_MULTIPLIER = {
    "LONG_SETUP": 1.00,
    "SHORT_SETUP": 1.00,
    "RESEARCH_BULLISH": 0.75,
    "RESEARCH_BEARISH": 0.75,
    "WAIT": 0.50,
    "UNAVAILABLE": 0.25,
}


def _ranking_dir(base_dir: str | Path | None = None) -> Path:
    if base_dir is not None:
        return Path(base_dir)
    override = os.getenv("MARKET_FORECASTER_RANKING_DIR")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[1] / ".local" / "opportunity_ranking"


def normalize_watchlist(values: str | Iterable[str], max_tickers: int = 30) -> list[str]:
    if isinstance(values, str):
        raw = re.split(r"[\s,;]+", values)
    else:
        raw = [str(x) for x in values]

    result: list[str] = []
    seen = set()
    for item in raw:
        symbol = item.upper().strip()
        if not symbol or symbol in seen:
            continue
        if not _TICKER_RE.fullmatch(symbol):
            continue
        seen.add(symbol)
        result.append(symbol)
        if len(result) >= max(1, int(max_tickers)):
            break
    return result


def save_watchlist(
    tickers: str | Iterable[str],
    *,
    base_dir: str | Path | None = None,
) -> list[str]:
    symbols = normalize_watchlist(tickers)
    root = _ranking_dir(base_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "watchlist.json"
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps({"tickers": symbols}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temp.replace(path)
    return symbols


def load_watchlist(
    *,
    base_dir: str | Path | None = None,
    default: Iterable[str] | None = None,
) -> list[str]:
    path = _ranking_dir(base_dir) / "watchlist.json"
    if not path.exists():
        return normalize_watchlist(default or [])
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return normalize_watchlist(payload.get("tickers", []))
    except Exception:
        return normalize_watchlist(default or [])


def _decision_row(snapshot: dict) -> dict | None:
    horizons = snapshot.get("horizons", []) or []
    if not horizons:
        return None

    primary = snapshot.get("primary_horizon")
    if primary is not None:
        for row in horizons:
            if int(row.get("horizon", 0) or 0) == int(primary):
                return row

    return max(
        horizons,
        key=lambda row: float(row.get("opportunity_score", 0.0) or 0.0),
    )


def _age_hours(timestamp: str | None, now: datetime) -> float | None:
    if not timestamp:
        return None
    ts = pd.to_datetime(timestamp, errors="coerce", utc=True)
    if pd.isna(ts):
        return None
    return max(0.0, (pd.Timestamp(now) - ts).total_seconds() / 3600.0)


def _staleness_multiplier(age_hours: float | None) -> float:
    if age_hours is None:
        return 0.60
    if age_hours <= 36:
        return 1.00
    if age_hours <= 72:
        return 0.90
    if age_hours <= 168:
        return 0.70
    return 0.40


def _direction_bucket(row: dict) -> str:
    recommendation = str(row.get("recommendation", "")).upper()
    direction = str(row.get("direction", "")).upper()
    if recommendation == "LONG_SETUP" or direction == "BULLISH":
        return "LONG"
    if recommendation == "SHORT_SETUP" or direction == "BEARISH":
        return "SHORT"
    return "NEUTRAL"


def _candidate_from_snapshot(ticker: str, snapshot: dict, now: datetime) -> dict | None:
    row = _decision_row(snapshot)
    if row is None:
        return None

    evidence = str(row.get("evidence_status", "PROVISIONAL")).upper()
    data_mode = str(snapshot.get("data_mode", "LIVE_PRIMARY")).upper()
    drift = str(snapshot.get("drift_status", "COLLECTING")).upper()
    recommendation = str(row.get("recommendation", "WAIT")).upper()

    raw_score = float(row.get("opportunity_score", 0.0) or 0.0)
    age = _age_hours(snapshot.get("generated_at_utc"), now)

    evidence_mult = EVIDENCE_MULTIPLIER.get(evidence, 0.35)
    data_mult = DATA_MULTIPLIER.get(data_mode, 0.70)
    drift_mult = DRIFT_MULTIPLIER.get(drift, 0.60)
    rec_mult = RECOMMENDATION_MULTIPLIER.get(recommendation, 0.50)
    stale_mult = _staleness_multiplier(age)

    base_adjusted = raw_score * evidence_mult * data_mult * drift_mult * rec_mult * stale_mult

    return {
        "ticker": ticker,
        "horizon": int(row.get("horizon", 0) or 0),
        "target_date": row.get("target_date"),
        "recommendation": recommendation,
        "actionable": bool(row.get("actionable", False)),
        "direction": str(row.get("direction", "NEUTRAL")).upper(),
        "direction_bucket": _direction_bucket(row),
        "opportunity_score": raw_score,
        "base_adjusted_score": float(base_adjusted),
        "evidence_status": evidence,
        "resolved_observations": int(row.get("resolved_observations", 0) or 0),
        "unique_market_snapshots": int(row.get("unique_market_snapshots", 0) or 0),
        "expected_return_pct": float(row.get("calibrated_expected_return_pct", 0.0) or 0.0),
        "probability_up_pct": row.get("probability_up_pct"),
        "reward_risk": row.get("reward_risk"),
        "reference_entry": row.get("reference_entry"),
        "decision_target": row.get("decision_target"),
        "invalidation": row.get("invalidation"),
        "data_mode": data_mode,
        "drift_status": drift,
        "policy_status": str(snapshot.get("policy_status", "UNKNOWN")),
        "effective_champion": str(snapshot.get("effective_champion", "UNKNOWN")),
        "decision_age_hours": age,
        "evidence_multiplier": evidence_mult,
        "data_multiplier": data_mult,
        "drift_multiplier": drift_mult,
        "recommendation_multiplier": rec_mult,
        "staleness_multiplier": stale_mult,
    }


def _close_series(frame: pd.DataFrame, ticker: str) -> pd.Series | None:
    if frame is None or frame.empty or "Date" not in frame.columns or "Close" not in frame.columns:
        return None
    close = frame["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    dates = pd.to_datetime(frame["Date"], errors="coerce")
    try:
        dates = dates.dt.tz_localize(None)
    except TypeError:
        pass
    series = pd.Series(pd.to_numeric(close, errors="coerce").to_numpy(), index=dates, name=ticker)
    series = series.dropna()
    return series if len(series) >= 21 else None


def build_return_correlation(
    tickers: Iterable[str],
    *,
    period: str = "6mo",
) -> tuple[dict[str, dict[str, float | None]], dict[str, int]]:
    series: list[pd.Series] = []
    rows_by_ticker: dict[str, int] = {}

    for ticker in normalize_watchlist(tickers):
        try:
            frame = fetch_stock_data(ticker, period, "1d")
            close = _close_series(frame, ticker)
            if close is None:
                rows_by_ticker[ticker] = 0
                continue
            returns = close.pct_change().dropna()
            rows_by_ticker[ticker] = int(len(returns))
            if len(returns) >= 20:
                series.append(returns)
        except Exception:
            rows_by_ticker[ticker] = 0

    if len(series) < 2:
        return {}, rows_by_ticker

    merged = pd.concat(series, axis=1, join="outer")
    corr = merged.corr(min_periods=20)
    matrix: dict[str, dict[str, float | None]] = {}
    for left in corr.columns:
        matrix[left] = {}
        for right in corr.columns:
            value = corr.loc[left, right]
            matrix[left][right] = None if pd.isna(value) else float(value)
    return matrix, rows_by_ticker


def _corr_value(matrix: dict, left: str, right: str) -> float | None:
    try:
        value = matrix.get(left, {}).get(right)
        if value is None:
            return None
        value = float(value)
        return value if np.isfinite(value) else None
    except Exception:
        return None


def _apply_correlation_penalty(rows: list[dict], matrix: dict) -> list[dict]:
    ordered = sorted(rows, key=lambda row: row["base_adjusted_score"], reverse=True)
    higher: list[dict] = []

    for row in ordered:
        positive_corrs = []
        if row["direction_bucket"] != "NEUTRAL":
            for prior in higher:
                if prior["direction_bucket"] != row["direction_bucket"]:
                    continue
                corr = _corr_value(matrix, row["ticker"], prior["ticker"])
                if corr is not None and corr > 0:
                    positive_corrs.append(corr)

        max_corr = max(positive_corrs) if positive_corrs else None
        penalty = 1.0
        if max_corr is not None and max_corr > 0.60:
            severity = min(1.0, max(0.0, (max_corr - 0.60) / 0.40))
            penalty = 1.0 - 0.25 * severity

        row["max_same_direction_correlation"] = max_corr
        row["correlation_multiplier"] = float(penalty)
        row["correlation_penalty_pct"] = float((1.0 - penalty) * 100.0)
        row["ranking_score"] = float(row["base_adjusted_score"] * penalty)
        higher.append(row)

    return sorted(ordered, key=lambda row: row["ranking_score"], reverse=True)


def _assign_risk_budget(rows: list[dict], max_single_pct: float = 25.0) -> float:
    actionable = [
        row for row in rows
        if row.get("actionable")
        and row.get("evidence_status") == "CALIBRATED"
        and row.get("data_mode") != "CACHE_FALLBACK"
        and row.get("drift_status") not in {"DEGRADED", "FROZEN"}
        and float(row.get("ranking_score", 0.0)) > 0
    ]

    total = sum(float(row["ranking_score"]) for row in actionable)
    for row in rows:
        row["research_risk_budget_pct"] = 0.0

    if total <= 0:
        return 100.0

    allocated = 0.0
    for row in actionable:
        raw_share = float(row["ranking_score"]) / total * 100.0
        cap = float(max_single_pct)
        corr = row.get("max_same_direction_correlation")
        if corr is not None and float(corr) >= 0.85:
            cap = min(cap, 15.0)
        share = min(raw_share, cap)
        row["research_risk_budget_pct"] = float(share)
        allocated += share

    return float(max(0.0, 100.0 - allocated))


def rank_watchlist(
    tickers: str | Iterable[str],
    *,
    include_correlation: bool = True,
    correlation_period: str = "6mo",
    max_single_risk_budget_pct: float = 25.0,
    ranking_dir: str | Path | None = None,
    decision_dir: str | Path | None = None,
    now: datetime | None = None,
) -> dict:
    symbols = normalize_watchlist(tickers)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)

    rows = []
    missing = []
    for ticker in symbols:
        snapshot = load_decision_snapshot(ticker, base_dir=decision_dir)
        if not snapshot:
            missing.append(ticker)
            continue
        candidate = _candidate_from_snapshot(ticker, snapshot, current)
        if candidate is None:
            missing.append(ticker)
            continue
        rows.append(candidate)

    matrix: dict[str, dict[str, float | None]] = {}
    correlation_rows: dict[str, int] = {}
    if include_correlation and len(rows) >= 2:
        matrix, correlation_rows = build_return_correlation(
            [row["ticker"] for row in rows],
            period=correlation_period,
        )

    ranked = _apply_correlation_penalty(rows, matrix)
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index

    unallocated = _assign_risk_budget(
        ranked,
        max_single_pct=max_single_risk_budget_pct,
    )

    actionable_count = sum(1 for row in ranked if row.get("actionable"))
    calibrated_count = sum(1 for row in ranked if row.get("evidence_status") == "CALIBRATED")

    result = {
        "generated_at_utc": current.isoformat(),
        "watchlist": symbols,
        "coverage_count": len(ranked),
        "missing_decisions": missing,
        "actionable_count": actionable_count,
        "calibrated_count": calibrated_count,
        "correlation_enabled": bool(include_correlation),
        "correlation_period": correlation_period,
        "correlation_matrix": matrix,
        "correlation_return_rows": correlation_rows,
        "max_single_risk_budget_pct": float(max_single_risk_budget_pct),
        "unallocated_research_risk_budget_pct": unallocated,
        "ranked": ranked,
        "notes": [
            "Ranking consumes persisted governed 3.3 decision snapshots; it does not run forecasts.",
            "Weak evidence, fallback/cached data, drift, stale snapshots, and same-direction correlation reduce ranking score.",
            "Research risk-budget shares are relative concentration caps and are not trade execution instructions.",
            "Missing tickers need their own governed Ensemble forecast before they can be ranked.",
        ],
    }
    persist_ranking_snapshot(result, base_dir=ranking_dir)
    return result


def persist_ranking_snapshot(result: dict, *, base_dir: str | Path | None = None) -> Path:
    root = _ranking_dir(base_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "latest.json"
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")
    temp.replace(path)
    return path


def load_ranking_snapshot(*, base_dir: str | Path | None = None) -> dict:
    path = _ranking_dir(base_dir) / "latest.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}
