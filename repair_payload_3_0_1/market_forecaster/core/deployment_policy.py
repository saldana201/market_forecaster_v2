"""Drift monitoring and explicit production deployment policy.

This layer consumes the append-only forecast/outcome ledgers introduced in 2.9.

Policy:
- The default/incumbent champion is adaptive_production_consensus.
- Governance recommendations alone never switch production.
- Challenger promotion requires explicit approval with approver + rationale.
- Challengers are drift-monitored using recent realized outcomes versus an older
  reference window.
- A severely degraded approved challenger is frozen automatically and the
  effective production path falls back to the incumbent.
- Approval history is append-only; a freeze never rewrites past decisions.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from market_forecaster.core.forecast_audit import (
    INCUMBENT_CANDIDATE,
    governance_summary,
    load_audit_outcomes,
    load_audit_runs,
)

CANDIDATES = (
    "validated_ensemble",
    "pre_options_consensus",
    "adaptive_production_consensus",
)
DEFAULT_CHAMPION = INCUMBENT_CANDIDATE


@dataclass
class DeploymentDecision:
    ticker: str
    approved_champion: str
    effective_champion: str
    policy_status: str
    drift_status: str
    dates: pd.DatetimeIndex
    path: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    approval_event_id: str | None
    notes: list[str]

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "approved_champion": self.approved_champion,
            "effective_champion": self.effective_champion,
            "policy_status": self.policy_status,
            "drift_status": self.drift_status,
            "dates": [pd.Timestamp(x).isoformat() for x in self.dates],
            "path": [float(x) for x in self.path],
            "lower": [None if not np.isfinite(x) else float(x) for x in self.lower],
            "upper": [None if not np.isfinite(x) else float(x) for x in self.upper],
            "approval_event_id": self.approval_event_id,
            "notes": list(self.notes),
        }


def _base_dir(base_dir: str | Path | None = None) -> Path:
    if base_dir is not None:
        return Path(base_dir)
    override = os.getenv("MARKET_FORECASTER_AUDIT_DIR")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[1] / ".local" / "forecast_audit"


def _events_path(ticker: str, base_dir: str | Path | None = None) -> Path:
    symbol = str(ticker or "").upper().strip()
    if not symbol:
        raise ValueError("ticker is required")
    path = _base_dir(base_dir) / "governance" / f"{symbol}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_governance_events(
    ticker: str,
    *,
    base_dir: str | Path | None = None,
) -> list[dict]:
    path = _events_path(ticker, base_dir)
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def _append_event(
    ticker: str,
    event: dict,
    *,
    base_dir: str | Path | None = None,
) -> dict:
    path = _events_path(ticker, base_dir)
    event = dict(event)
    event["ticker"] = str(ticker).upper().strip()
    event["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    event["event_id"] = _hash({
        "ticker": event["ticker"],
        "event_type": event.get("event_type"),
        "candidate": event.get("candidate"),
        "created_at_utc": event["created_at_utc"],
        "approved_by": event.get("approved_by"),
        "rationale": event.get("rationale"),
    })[:24]
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
    return event


def current_approval(
    ticker: str,
    *,
    base_dir: str | Path | None = None,
) -> dict:
    events = load_governance_events(ticker, base_dir=base_dir)
    approvals = [e for e in events if e.get("event_type") == "APPROVE_CHAMPION"]
    if not approvals:
        return {
            "candidate": DEFAULT_CHAMPION,
            "event_id": None,
            "approved_by": "SYSTEM_DEFAULT",
            "rationale": "Default production incumbent",
            "created_at_utc": None,
        }
    return approvals[-1]


def _latest_runs(runs: list[dict]) -> list[dict]:
    selected = {}
    for run in runs:
        key = str(
            run.get("market_last_timestamp")
            or run.get("created_at_utc")
            or run.get("run_id")
        )
        current = selected.get(key)
        if current is None or str(run.get("created_at_utc", "")) >= str(current.get("created_at_utc", "")):
            selected[key] = run
    return list(selected.values())


def _candidate_observations(runs: list[dict], outcomes: list[dict]) -> list[dict]:
    latest = _latest_runs(runs)
    run_map = {str(r.get("run_id")): r for r in latest}
    rows = []
    for outcome in outcomes:
        run_id = str(outcome.get("run_id", ""))
        run = run_map.get(run_id)
        if run is None:
            continue
        realized_date = pd.to_datetime(outcome.get("realized_date"), errors="coerce")
        if pd.isna(realized_date):
            realized_date = pd.to_datetime(outcome.get("target_date"), errors="coerce")
        for candidate, score in (outcome.get("candidate_scores", {}) or {}).items():
            try:
                error = float(score.get("absolute_return_error"))
            except Exception:
                continue
            if not np.isfinite(error):
                continue
            rows.append({
                "candidate": str(candidate),
                "run_id": run_id,
                "horizon": int(outcome.get("horizon", 0) or 0),
                "regime": str(run.get("current_regime", "UNKNOWN")),
                "realized_date": realized_date,
                "absolute_return_error": error,
                "direction_correct": bool(score.get("direction_correct", False)),
            })
    rows.sort(key=lambda r: pd.Timestamp.min if pd.isna(r["realized_date"]) else r["realized_date"])
    return rows


def _drift_status(
    candidate: str,
    recent_mae: float,
    reference_mae: float,
    recent_direction: float,
    reference_direction: float,
) -> tuple[str, float, float]:
    degradation = (
        (recent_mae - reference_mae) / reference_mae * 100.0
        if np.isfinite(reference_mae) and reference_mae > 1e-12
        else 0.0
    )
    direction_drop = reference_direction - recent_direction
    severe = degradation >= 50.0 or (direction_drop >= 15.0 and recent_direction < 45.0)
    moderate = degradation >= 25.0 or direction_drop >= 10.0

    if candidate != DEFAULT_CHAMPION and severe:
        return "FROZEN", float(degradation), float(direction_drop)
    if severe:
        return "DEGRADED", float(degradation), float(direction_drop)
    if moderate:
        return "WATCH", float(degradation), float(direction_drop)
    return "HEALTHY", float(degradation), float(direction_drop)


def drift_report(
    runs: list[dict],
    outcomes: list[dict],
    *,
    recent_window: int = 10,
    reference_window: int = 20,
    min_recent: int = 5,
    min_reference: int = 10,
) -> dict:
    """Compare recent realized performance with an older non-overlapping window."""
    observations = _candidate_observations(runs, outcomes)
    candidates = sorted({r["candidate"] for r in observations} | set(CANDIDATES))
    summary = []
    segments = []

    def evaluate_group(candidate: str, rows: list[dict], *, min_r: int, min_ref: int) -> dict:
        rows = sorted(
            rows,
            key=lambda r: pd.Timestamp.min if pd.isna(r["realized_date"]) else r["realized_date"],
        )
        recent = rows[-recent_window:]
        older_pool = rows[:-len(recent)] if recent else rows
        reference = older_pool[-reference_window:]
        if len(recent) < min_r or len(reference) < min_ref:
            return {
                "candidate": candidate,
                "status": "COLLECTING",
                "recent_observations": len(recent),
                "reference_observations": len(reference),
                "recent_mae_bps": None,
                "reference_mae_bps": None,
                "degradation_pct": None,
                "recent_direction_pct": None,
                "reference_direction_pct": None,
                "direction_drop_pp": None,
            }

        recent_mae = float(np.mean([x["absolute_return_error"] for x in recent]))
        reference_mae = float(np.mean([x["absolute_return_error"] for x in reference]))
        recent_dir = float(np.mean([x["direction_correct"] for x in recent]) * 100.0)
        reference_dir = float(np.mean([x["direction_correct"] for x in reference]) * 100.0)
        status, degradation, direction_drop = _drift_status(
            candidate, recent_mae, reference_mae, recent_dir, reference_dir
        )
        return {
            "candidate": candidate,
            "status": status,
            "recent_observations": len(recent),
            "reference_observations": len(reference),
            "recent_mae_bps": recent_mae * 10000.0,
            "reference_mae_bps": reference_mae * 10000.0,
            "degradation_pct": degradation,
            "recent_direction_pct": recent_dir,
            "reference_direction_pct": reference_dir,
            "direction_drop_pp": direction_drop,
        }

    for candidate in candidates:
        rows = [r for r in observations if r["candidate"] == candidate]
        summary.append(evaluate_group(candidate, rows, min_r=min_recent, min_ref=min_reference))
        for horizon, regime in sorted({(r["horizon"], r["regime"]) for r in rows}):
            group = [r for r in rows if r["horizon"] == horizon and r["regime"] == regime]
            segment = evaluate_group(candidate, group, min_r=3, min_ref=4)
            segment["horizon"] = horizon
            segment["regime"] = regime
            segments.append(segment)

    return {
        "recent_window": int(recent_window),
        "reference_window": int(reference_window),
        "summary": summary,
        "segments": segments,
    }


def _drift_row(report: dict, candidate: str) -> dict:
    return next(
        (r for r in report.get("summary", []) if r.get("candidate") == candidate),
        {"candidate": candidate, "status": "COLLECTING", "recent_observations": 0, "reference_observations": 0},
    )


def deployment_policy_state(
    ticker: str,
    *,
    base_dir: str | Path | None = None,
    runs: list[dict] | None = None,
    outcomes: list[dict] | None = None,
) -> dict:
    runs = load_audit_runs(ticker, base_dir=base_dir) if runs is None else runs
    outcomes = load_audit_outcomes(ticker, base_dir=base_dir) if outcomes is None else outcomes
    governance = governance_summary(runs, outcomes)
    drift = drift_report(runs, outcomes)
    approval = current_approval(ticker, base_dir=base_dir)

    approved = str(approval.get("candidate", DEFAULT_CHAMPION))
    if approved not in CANDIDATES:
        approved = DEFAULT_CHAMPION
    approved_drift = _drift_row(drift, approved)
    effective = approved
    policy_status = "APPROVED" if approval.get("event_id") else "DEFAULT_INCUMBENT"
    notes = []

    if approved != DEFAULT_CHAMPION and approved_drift.get("status") == "FROZEN":
        effective = DEFAULT_CHAMPION
        policy_status = "FROZEN_FALLBACK"
        notes.append(
            f"Approved challenger {approved} is frozen by drift policy; "
            f"effective deployment falls back to {DEFAULT_CHAMPION}."
        )

    incumbent_drift = _drift_row(drift, DEFAULT_CHAMPION)
    if incumbent_drift.get("status") == "DEGRADED":
        notes.append(
            "The incumbent itself is materially degraded. 3.0 raises an alert "
            "but does not auto-select a challenger without approval."
        )

    return {
        "ticker": str(ticker).upper().strip(),
        "approved_champion": approved,
        "effective_champion": effective,
        "policy_status": policy_status,
        "approval": approval,
        "governance": governance,
        "drift": drift,
        "approved_drift": approved_drift,
        "incumbent_drift": incumbent_drift,
        "notes": notes,
        "candidate_choices": list(CANDIDATES),
    }


def validate_champion_approval(
    ticker: str,
    candidate: str,
    approved_by: str,
    rationale: str,
    *,
    base_dir: str | Path | None = None,
    runs: list[dict] | None = None,
    outcomes: list[dict] | None = None,
) -> tuple[bool, str, dict]:
    candidate = str(candidate or "").strip()
    approved_by = str(approved_by or "").strip()
    rationale = str(rationale or "").strip()
    if candidate not in CANDIDATES:
        return False, "Unknown deployment candidate", {}
    if len(approved_by) < 2:
        return False, "Approver name/identifier is required", {}
    if len(rationale) < 10:
        return False, "Approval rationale must be at least 10 characters", {}

    state = deployment_policy_state(
        ticker, base_dir=base_dir, runs=runs, outcomes=outcomes
    )
    if candidate == DEFAULT_CHAMPION:
        return True, "Incumbent approval/rollback is allowed explicitly", state

    drift = _drift_row(state["drift"], candidate)
    if drift.get("status") in {"FROZEN", "COLLECTING"}:
        return False, f"Candidate drift status is {drift.get('status')}", state

    governance = state["governance"]
    if governance.get("recommendation") != "REVIEW_CHALLENGER_PROMOTION":
        return False, "Governance has not recommended challenger promotion", state
    if governance.get("observed_leader") != candidate:
        return False, "Candidate is not the current eligible realized-performance leader", state
    row = next(
        (x for x in governance.get("leaderboard", []) if x.get("candidate") == candidate),
        None,
    )
    if not row or not row.get("eligible"):
        return False, "Candidate has not met governance evidence minimums", state
    return True, "Approval gates satisfied", state


def approve_champion(
    ticker: str,
    candidate: str,
    approved_by: str,
    rationale: str,
    *,
    base_dir: str | Path | None = None,
) -> dict:
    ok, reason, state = validate_champion_approval(
        ticker, candidate, approved_by, rationale, base_dir=base_dir
    )
    if not ok:
        raise ValueError(reason)
    governance = state.get("governance", {})
    return _append_event(
        ticker,
        {
            "event_type": "APPROVE_CHAMPION",
            "candidate": candidate,
            "approved_by": str(approved_by).strip(),
            "rationale": str(rationale).strip(),
            "evidence": {
                "governance_status": governance.get("status"),
                "observed_leader": governance.get("observed_leader"),
                "improvement_vs_incumbent_pct": governance.get("improvement_vs_incumbent_pct"),
                "drift_status": _drift_row(state.get("drift", {}), candidate).get("status"),
            },
        },
        base_dir=base_dir,
    )


def build_deployment_decision(
    ticker: str,
    adaptive_result: Any,
    *,
    base_dir: str | Path | None = None,
) -> DeploymentDecision:
    state = deployment_policy_state(ticker, base_dir=base_dir)
    dates = pd.DatetimeIndex(pd.to_datetime(getattr(adaptive_result, "dates", [])))
    ensemble = np.asarray(getattr(adaptive_result, "ensemble", []), dtype=float)
    pre_options = np.asarray(getattr(adaptive_result, "base_consensus", ensemble), dtype=float)
    adaptive = np.asarray(getattr(adaptive_result, "consensus", pre_options), dtype=float)
    if len(dates) == 0 or len(adaptive) != len(dates):
        raise ValueError("Deployment policy requires an aligned adaptive consensus result")

    paths = {
        "validated_ensemble": ensemble,
        "pre_options_consensus": pre_options,
        "adaptive_production_consensus": adaptive,
    }
    effective = state["effective_champion"]
    path = np.asarray(paths.get(effective, adaptive), dtype=float)
    if len(path) != len(dates) or not np.isfinite(path).all() or (path <= 0).any():
        effective = DEFAULT_CHAMPION
        path = adaptive.copy()

    adaptive_lower = np.asarray(getattr(adaptive_result, "lower", []), dtype=float)
    adaptive_upper = np.asarray(getattr(adaptive_result, "upper", []), dtype=float)
    if len(adaptive_lower) != len(path) or len(adaptive_upper) != len(path):
        lower = np.full(len(path), np.nan)
        upper = np.full(len(path), np.nan)
    else:
        lower_ratio = adaptive_lower / adaptive
        upper_ratio = adaptive_upper / adaptive
        lower = path * lower_ratio
        upper = path * upper_ratio

    approval = state.get("approval", {})
    notes = list(state.get("notes", []))
    notes.append("Production champion changes require an explicit append-only approval event.")
    notes.append("Frozen challengers fall back to the incumbent without deleting approval history.")
    return DeploymentDecision(
        ticker=str(ticker).upper().strip(),
        approved_champion=state["approved_champion"],
        effective_champion=effective,
        policy_status=state["policy_status"],
        drift_status=str(state.get("approved_drift", {}).get("status", "COLLECTING")),
        dates=dates,
        path=path,
        lower=lower,
        upper=upper,
        approval_event_id=approval.get("event_id"),
        notes=notes,
    )
