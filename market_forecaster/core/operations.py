"""Production operations monitoring for Market Forecaster 3.1."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from market_forecaster.core.deployment_policy import deployment_policy_state
from market_forecaster.core.forecast_audit import audit_snapshot, reconcile_matured_outcomes

DEFAULT_CADENCE_MINUTES = 30


def _ops_dir(base_dir=None) -> Path:
    if base_dir is not None:
        return Path(base_dir)
    override = os.getenv("MARKET_FORECASTER_OPERATIONS_DIR")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[1] / ".local" / "operations"


def _now(value=None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _symbol(ticker: str) -> str:
    value = str(ticker or "").upper().strip()
    if not value:
        raise ValueError("ticker is required")
    return value


def _events_path(base_dir=None) -> Path:
    path = _ops_dir(base_dir) / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _state_path(ticker, base_dir=None) -> Path:
    path = _ops_dir(base_dir) / "state" / f"{_symbol(ticker)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _safe(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
        return value if np.isfinite(value) else None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.ndarray):
        return [_safe(x) for x in value.tolist()]
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def record_operation_event(ticker, component, status, message, *, metadata=None, base_dir=None, now=None):
    event = {
        "ticker": _symbol(ticker),
        "component": str(component),
        "status": str(status).upper(),
        "message": str(message),
        "metadata": _safe(metadata or {}),
        "created_at_utc": _now(now).isoformat(),
    }
    raw = json.dumps(event, sort_keys=True, separators=(",", ":"))
    event["event_id"] = hashlib.sha256(raw.encode()).hexdigest()[:24]
    with _events_path(base_dir).open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
    return event


def load_operation_events(ticker=None, *, limit=500, base_dir=None):
    path = _events_path(base_dir)
    if not path.exists():
        return []
    symbol = str(ticker or "").upper().strip()
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict) and (not symbol or str(row.get("ticker", "")).upper() == symbol):
            rows.append(row)
    return rows[-max(1, int(limit)):]


def load_operations_state(ticker, *, base_dir=None):
    path = _state_path(ticker, base_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_state(ticker, state, *, base_dir=None):
    path = _state_path(ticker, base_dir)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(_safe(state), indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def assess_data_freshness(ticker, stock_df, *, now=None):
    symbol = _symbol(ticker)
    provider = getattr(stock_df, "attrs", {}).get("provider") if stock_df is not None else None
    if stock_df is None or getattr(stock_df, "empty", True) or "Date" not in stock_df.columns:
        return {"status": "UNKNOWN", "last_market_date": None, "age": None, "age_unit": None,
                "provider": provider, "reason": "No market data available"}

    dates = pd.to_datetime(stock_df["Date"], errors="coerce").dropna()
    if dates.empty:
        return {"status": "UNKNOWN", "last_market_date": None, "age": None, "age_unit": None,
                "provider": provider, "reason": "No usable Date values"}
    try:
        dates = dates.dt.tz_localize(None)
    except TypeError:
        pass
    last_date = pd.Timestamp(dates.max()).normalize()
    today = pd.Timestamp(_now(now)).tz_localize(None).normalize()

    if symbol.endswith("-USD"):
        age = max(0, int((today - last_date).days))
        status = "OK" if age <= 1 else ("WARN" if age == 2 else "STALE")
        unit = "calendar_days"
    else:
        age = max(0, int(np.busday_count(np.datetime64(last_date.date()), np.datetime64(today.date()))))
        status = "OK" if age <= 1 else ("WARN" if age == 2 else "STALE")
        unit = "business_days"

    return {
        "status": status, "last_market_date": last_date.date().isoformat(),
        "age": age, "age_unit": unit, "provider": provider,
        "reason": f"Latest market row is {age} {unit.replace('_', ' ')} old",
    }


def _cycle_due(last_run, cadence_minutes, now):
    if not last_run:
        return True
    ts = pd.to_datetime(last_run, errors="coerce", utc=True)
    if pd.isna(ts):
        return True
    return (pd.Timestamp(now) - ts).total_seconds() / 60 >= max(1, int(cadence_minutes))


def run_operations_cycle(ticker, stock_df, *, force=False, cadence_minutes=DEFAULT_CADENCE_MINUTES,
                         base_dir=None, now=None):
    symbol = _symbol(ticker)
    current = _now(now)
    previous = load_operations_state(symbol, base_dir=base_dir)
    if not force and not _cycle_due(previous.get("last_run_utc"), cadence_minutes, current):
        result = dict(previous)
        result["cycle_status"] = "SKIPPED_CADENCE"
        return result

    errors = []
    freshness = assess_data_freshness(symbol, stock_df, now=current)
    reconciliation = {"created": 0, "matured": 0, "pending": 0}

    if stock_df is not None and not getattr(stock_df, "empty", True):
        try:
            reconciliation = reconcile_matured_outcomes(symbol, stock_df)
        except Exception as exc:
            errors.append(f"reconciliation: {exc}")
    else:
        errors.append("reconciliation: market data unavailable")

    try:
        audit = audit_snapshot(symbol)
    except Exception as exc:
        audit = {"runs": 0, "targets": 0, "resolved_targets": 0, "pending_targets": 0}
        errors.append(f"audit: {exc}")

    try:
        deployment = deployment_policy_state(symbol)
        dep = {
            "approved_champion": deployment.get("approved_champion"),
            "effective_champion": deployment.get("effective_champion"),
            "policy_status": deployment.get("policy_status"),
            "approved_drift_status": (deployment.get("approved_drift") or {}).get("status"),
            "incumbent_drift_status": (deployment.get("incumbent_drift") or {}).get("status"),
            "governance_recommendation": (deployment.get("governance") or {}).get("recommendation"),
        }
    except Exception as exc:
        dep = {"policy_status": "UNKNOWN", "approved_drift_status": "UNKNOWN",
               "incumbent_drift_status": "UNKNOWN"}
        errors.append(f"deployment: {exc}")

    state = {
        "ticker": symbol,
        "last_run_utc": current.isoformat(),
        "cycle_status": "SUCCESS" if not errors else "PARTIAL_ERROR",
        "cadence_minutes": int(cadence_minutes),
        "freshness": freshness,
        "reconciliation": reconciliation,
        "audit": {
            "runs": int(audit.get("runs", 0) or 0),
            "targets": int(audit.get("targets", 0) or 0),
            "resolved_targets": int(audit.get("resolved_targets", 0) or 0),
            "pending_targets": int(audit.get("pending_targets", 0) or 0),
        },
        "deployment": dep,
        "errors": errors,
    }
    _write_state(symbol, state, base_dir=base_dir)
    record_operation_event(
        symbol, "maintenance", "SUCCESS" if not errors else "ERROR",
        "Operations maintenance cycle completed" if not errors else "Operations maintenance cycle completed with errors",
        metadata=state, base_dir=base_dir, now=current,
    )
    return state


def _recent_errors(events, hours, now):
    cutoff = pd.Timestamp(now) - pd.Timedelta(hours=hours)
    result = []
    for event in events:
        if str(event.get("status", "")).upper() not in {"ERROR", "FAILED", "FAILURE"}:
            continue
        ts = pd.to_datetime(event.get("created_at_utc"), errors="coerce", utc=True)
        if pd.notna(ts) and ts >= cutoff:
            result.append(event)
    return result


def operations_health(ticker, stock_df=None, *, base_dir=None, now=None):
    symbol = _symbol(ticker)
    current = _now(now)
    state = load_operations_state(symbol, base_dir=base_dir)
    events = load_operation_events(symbol, limit=1000, base_dir=base_dir)
    freshness = assess_data_freshness(symbol, stock_df, now=current) if stock_df is not None else state.get("freshness", {})
    errors24 = _recent_errors(events, 24, current)
    errors7d = _recent_errors(events, 168, current)

    try:
        audit = audit_snapshot(symbol)
    except Exception:
        audit = state.get("audit", {}) or {}

    try:
        deployment = deployment_policy_state(symbol)
        policy_status = deployment.get("policy_status", "UNKNOWN")
        approved_drift = (deployment.get("approved_drift") or {}).get("status", "UNKNOWN")
        incumbent_drift = (deployment.get("incumbent_drift") or {}).get("status", "UNKNOWN")
    except Exception:
        deployment = {}
        policy_status = (state.get("deployment") or {}).get("policy_status", "UNKNOWN")
        approved_drift = (state.get("deployment") or {}).get("approved_drift_status", "UNKNOWN")
        incumbent_drift = (state.get("deployment") or {}).get("incumbent_drift_status", "UNKNOWN")

    provider_errors = [e for e in errors24 if e.get("component") in {"data_provider", "data_fetch"}]
    forecast_errors = [e for e in errors24 if e.get("component") in
                       {"forecast_pipeline", "ensemble", "options_flow", "sentiment", "seasonal"}]

    provider_status = "OK"
    if freshness.get("status") == "STALE" or len(provider_errors) >= 3:
        provider_status = "DEGRADED"
    elif freshness.get("status") in {"WARN", "UNKNOWN"} or provider_errors:
        provider_status = "WATCH"

    if stock_df is not None and not getattr(stock_df, "empty", True):
        if stock_df.attrs.get("is_cached") or stock_df.attrs.get("provider_failover_used") or stock_df.attrs.get("degraded_data"):
            provider_status = "WATCH"  # provider fallback/degraded data

    forecast_status = "DEGRADED" if len(forecast_errors) >= 3 else ("WATCH" if forecast_errors else "OK")
    audit_status = "NO_RUNS" if int(audit.get("runs", 0) or 0) == 0 else "ACTIVE"
    maintenance_status = str(state.get("cycle_status", "NOT_RUN"))
    severe_drift = approved_drift in {"FROZEN", "DEGRADED"} or incumbent_drift == "DEGRADED"

    if provider_status == "DEGRADED" or forecast_status == "DEGRADED" or severe_drift:
        overall = "DEGRADED"
    elif provider_status == "WATCH" or forecast_status == "WATCH" or approved_drift == "WATCH" or maintenance_status == "PARTIAL_ERROR":
        overall = "WATCH"
    elif maintenance_status == "NOT_RUN":
        overall = "COLLECTING"
    else:
        overall = "HEALTHY"

    by_component = {}
    for event in errors7d:
        component = str(event.get("component", "unknown"))
        by_component[component] = by_component.get(component, 0) + 1

    return {
        "ticker": symbol, "overall_status": overall,
        "provider_status": provider_status, "forecast_status": forecast_status,
        "audit_status": audit_status, "maintenance_status": maintenance_status,
        "freshness": freshness, "last_maintenance_utc": state.get("last_run_utc"),
        "errors_24h": len(errors24), "errors_7d": len(errors7d),
        "errors_7d_by_component": by_component,
        "audit": {
            "runs": int(audit.get("runs", 0) or 0),
            "targets": int(audit.get("targets", 0) or 0),
            "resolved_targets": int(audit.get("resolved_targets", 0) or 0),
            "pending_targets": int(audit.get("pending_targets", 0) or 0),
        },
        "deployment": {
            "policy_status": policy_status,
            "approved_drift_status": approved_drift,
            "incumbent_drift_status": incumbent_drift,
            "approved_champion": deployment.get("approved_champion"),
            "effective_champion": deployment.get("effective_champion"),
        },
        "recent_events": events[-50:],
        "generated_at_utc": current.isoformat(),
    }
