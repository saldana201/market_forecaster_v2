"""Canonical Forecast Contract for Market Forecaster 4.0.

This is the downstream boundary of Market Forecaster. It exposes forecasts,
uncertainty, calibration diagnostics, model/feature provenance, and data quality.
It intentionally excludes entries, exits, position sizing, orders, and portfolio
actions.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.feature_store import build_feature_store
from market_forecaster.core.forecast_authority import (
    authority_rows,
    load_authority_config,
    validate_authority_config,
)
from market_forecaster.core.market_context import build_market_context
from market_forecaster.core.research_snapshots import persist_forecast_contract
from market_forecaster.core.uncertainty_calibration import run_uncertainty_research

FORECAST_CONTRACT_SCHEMA_VERSION = "4.0-forecast-contract-v1"
FORBIDDEN_EXECUTION_FIELDS = {
    "entry",
    "exit",
    "stop_loss",
    "take_profit",
    "position_size",
    "order",
    "order_type",
    "shares",
    "quantity",
    "portfolio_weight",
    "trade",
}


def _clean_number(value):
    try:
        value = float(value)
        return value if np.isfinite(value) else None
    except Exception:
        return None


def _contract_id(payload: dict) -> str:
    material = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:24]


def _diagnostic_for_horizon(result: dict, horizon: int) -> dict:
    rows = [
        row for row in result.get("calibration_summaries", [])
        if int(row.get("horizon", -1)) == int(horizon)
    ]
    return dict(rows[0]) if rows else {}


def _current_for_horizon(result: dict, horizon: int) -> dict:
    rows = [
        row for row in result.get("current_forecasts", [])
        if int(row.get("horizon", -1)) == int(horizon)
    ]
    return dict(rows[0]) if rows else {}


def _build_forecast_row(
    *,
    horizon: int,
    authority: dict,
    current: dict,
    diagnostic: dict,
    feature_schema_version: str | None,
    context_info: dict | None,
) -> dict:
    row = {
        "horizon_days": int(horizon),
        "target_date": current.get("target_date"),
        "model": authority.get("model"),
        "context_family": authority.get("context_family", "none"),
        "sector_ticker": authority.get("sector_ticker"),
        "feature_schema_version": feature_schema_version,
        "expected_log_return": _clean_number(current.get("predicted_return")),
        "expected_return_pct": _clean_number(current.get("predicted_return_pct")),
        "projected_price": _clean_number(current.get("predicted_price")),
        "probability_up_pct": _clean_number(current.get("prob_up_pct")),
        "calibration_status": current.get("calibration_status"),
        "calibration_samples": int(current.get("calibration_samples", 0) or 0),
        "price_range_80": [
            _clean_number(current.get("lower_price_80")),
            _clean_number(current.get("upper_price_80")),
        ],
        "price_range_90": [
            _clean_number(current.get("lower_price_90")),
            _clean_number(current.get("upper_price_90")),
        ],
        "return_range_80_pct": [
            _clean_number(current.get("lower_return_pct_80")),
            _clean_number(current.get("upper_return_pct_80")),
        ],
        "return_range_90_pct": [
            _clean_number(current.get("lower_return_pct_90")),
            _clean_number(current.get("upper_return_pct_90")),
        ],
        "diagnostics": {
            "oos_records": int(diagnostic.get("oos_records", 0) or 0),
            "probability_eval_records": int(diagnostic.get("probability_eval_records", 0) or 0),
            "brier_score": _clean_number(diagnostic.get("brier_score")),
            "brier_skill_vs_50_pct": _clean_number(diagnostic.get("brier_skill_vs_50_pct")),
            "expected_calibration_error": _clean_number(diagnostic.get("expected_calibration_error")),
            "coverage_80_pct": _clean_number(diagnostic.get("coverage_80_pct")),
            "coverage_90_pct": _clean_number(diagnostic.get("coverage_90_pct")),
            "avg_width_bps_80": _clean_number(diagnostic.get("avg_width_bps_80")),
            "avg_width_bps_90": _clean_number(diagnostic.get("avg_width_bps_90")),
        },
        "context_provenance": {
            "available": bool(context_info.get("available")) if context_info else authority.get("context_family") == "none",
            "coverage_pct": _clean_number(context_info.get("coverage_pct")) if context_info else None,
            "sources_used": list(context_info.get("sources_used", [])) if context_info else [],
            "feature_count": int(context_info.get("feature_count", 0) or 0) if context_info else 0,
        },
    }
    return row


def assert_forecast_only_contract(contract: dict) -> None:
    """Reject accidental execution semantics anywhere in the canonical payload."""
    stack = [contract]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in FORBIDDEN_EXECUTION_FIELDS:
                    raise ValueError(f"Forecast Contract contains forbidden execution field: {key}")
                stack.append(item)
        elif isinstance(value, list):
            stack.extend(value)


def build_forecast_contract(
    ticker: str,
    *,
    period: str = "10y",
    authority_config: dict | None = None,
    n_splits: int = 6,
    test_size: int = 20,
    persist: bool = False,
    repo_root: str | Path | None = None,
    generated_at: str | None = None,
) -> dict:
    symbol = str(ticker or "").upper().strip()
    if not symbol:
        raise ValueError("Ticker is required")

    authority = authority_config or load_authority_config(
        repo_root=repo_root,
        require_available_models=True,
    )
    check = validate_authority_config(authority, require_available_models=True)
    if check["status"] != "PASS":
        raise ValueError("Forecast Authority is invalid: " + "; ".join(check["errors"]))
    authority = check["config"]

    market = fetch_stock_data(symbol, period, "1d")
    if market is None or market.empty:
        raise ValueError(f"No market data available for {symbol}")

    provider_attrs = dict(getattr(market, "attrs", {}))
    base_frame, metadata = build_feature_store(market, symbol)

    forecasts = []
    errors = []
    authority_used = []

    for row in authority_rows(authority):
        horizon = int(row["horizon"])
        if not row.get("enabled", True):
            continue

        model = str(row.get("model", "xgboost")).lower()
        context_family = str(row.get("context_family", "none")).lower()
        sector_ticker = row.get("sector_ticker")
        calibration_window = row.get("calibration_window", 120)

        feature_frame = base_frame
        context_info = None

        if context_family != "none":
            enriched, registry = build_market_context(
                base_frame,
                symbol,
                period=period,
                families=[context_family],
                sector_ticker=sector_ticker,
            )
            context_info = registry.get(context_family, {})
            if not context_info.get("available"):
                errors.append({
                    "horizon_days": horizon,
                    "model": model,
                    "context_family": context_family,
                    "error": "Configured context family is unavailable or lacks sufficient coverage",
                    "context_info": context_info,
                })
                continue
            feature_frame = enriched

        try:
            result = run_uncertainty_research(
                feature_frame,
                ticker=symbol,
                model=model,
                horizons=[horizon],
                n_splits=int(n_splits),
                test_size=int(test_size),
                calibration_window=calibration_window,
            )
            current = _current_for_horizon(result, horizon)
            if not current:
                raise RuntimeError("No current forecast produced")
            diagnostic = _diagnostic_for_horizon(result, horizon)

            forecasts.append(_build_forecast_row(
                horizon=horizon,
                authority=row,
                current=current,
                diagnostic=diagnostic,
                feature_schema_version=result.get("feature_schema_version"),
                context_info=context_info,
            ))
            authority_used.append({
                "horizon_days": horizon,
                "model": model,
                "context_family": context_family,
                "sector_ticker": sector_ticker,
                "calibration_window": calibration_window,
            })
        except Exception as exc:
            errors.append({
                "horizon_days": horizon,
                "model": model,
                "context_family": context_family,
                "error": str(exc),
            })

    enabled_count = sum(1 for row in authority_rows(authority) if row.get("enabled", True))
    if forecasts and len(forecasts) == enabled_count:
        status = "READY"
    elif forecasts:
        status = "PARTIAL"
    else:
        status = "UNAVAILABLE"

    generated = generated_at or datetime.now(timezone.utc).isoformat()
    current_price = _clean_number(base_frame.iloc[-1]["Close"]) if not base_frame.empty else None
    as_of = str(base_frame.iloc[-1]["Date"]) if not base_frame.empty else None

    core = {
        "schema_version": FORECAST_CONTRACT_SCHEMA_VERSION,
        "ticker": symbol,
        "as_of": as_of,
        "generated_at": generated,
        "status": status,
        "scope": "FORECAST_ONLY",
        "current_price": current_price,
        "forecasts": sorted(forecasts, key=lambda x: x["horizon_days"]),
        "authority": authority_used,
        "data_quality": {
            "provider": metadata.provider,
            "provider_failover_used": bool(metadata.provider_failover_used),
            "cache_used": bool(metadata.cache_used),
            "feature_store_rows": int(metadata.row_count),
            "feature_store_hash": metadata.dataset_hash,
            "raw_provider": provider_attrs.get("provider"),
            "cache_age_days": _clean_number(provider_attrs.get("cache_age_days")),
        },
        "errors": errors,
        "provenance": {
            "feature_store_schema": metadata.schema_version,
            "authority_schema": authority.get("schema_version"),
            "uncertainty_protocol": "3.9-calibration-uncertainty-v1",
            "contract_schema": FORECAST_CONTRACT_SCHEMA_VERSION,
        },
        "disclaimer": "Research and educational forecasting output only; no execution or investment instruction.",
    }

    core["contract_id"] = _contract_id(core)
    assert_forecast_only_contract(core)

    if persist:
        core["snapshot"] = persist_forecast_contract(core, repo_root=repo_root)

    return core
