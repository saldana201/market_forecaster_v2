"""Portfolio state + position-aware opportunity ranking (v3.5).

This layer consumes the 3.4 ranking and 3.3 decision snapshots. It never places
orders and never increases the 3.4 research risk budget.

Portfolio state is manual/local in v3.5:
- cash / unallocated capital
- ticker
- quantity (positive=long, negative=short)
- average cost basis

Position-aware controls:
- existing single-name concentration
- correlated same-direction exposure
- current position side vs candidate direction
- decision-layer invalidation breaches
- existing unrealized P/L / cost basis context

Runtime state:
    market_forecaster/.local/portfolio/state.json
    market_forecaster/.local/portfolio/latest_overlay.json
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
from market_forecaster.core.opportunity_ranking import (
    build_return_correlation,
    load_ranking_snapshot,
    normalize_watchlist,
)

_TICKER_RE = re.compile(r"^[A-Z0-9.^=_-]{1,24}$")


def _portfolio_dir(base_dir: str | Path | None = None) -> Path:
    if base_dir is not None:
        return Path(base_dir)
    override = os.getenv("MARKET_FORECASTER_PORTFOLIO_DIR")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[1] / ".local" / "portfolio"


def _finite(value: Any, default: float | None = None) -> float | None:
    try:
        value = float(value)
    except Exception:
        return default
    return value if np.isfinite(value) else default


def normalize_positions(positions: Iterable[dict] | None) -> list[dict]:
    normalized: list[dict] = []
    seen = set()

    for raw in positions or []:
        ticker = str(raw.get("ticker", "")).upper().strip()
        quantity = _finite(raw.get("quantity"), 0.0) or 0.0
        cost_basis = _finite(raw.get("cost_basis"))

        if not ticker and abs(quantity) <= 1e-12:
            continue
        if not ticker or not _TICKER_RE.fullmatch(ticker):
            raise ValueError(f"Invalid portfolio ticker: {ticker or '<blank>'}")
        if ticker in seen:
            raise ValueError(
                f"Duplicate portfolio ticker {ticker}; use one aggregated row per symbol"
            )
        if abs(quantity) <= 1e-12:
            raise ValueError(f"Quantity for {ticker} must be non-zero")
        if cost_basis is None or cost_basis <= 0:
            raise ValueError(f"Cost basis for {ticker} must be greater than zero")

        seen.add(ticker)
        normalized.append({
            "ticker": ticker,
            "quantity": float(quantity),
            "cost_basis": float(cost_basis),
        })

    return normalized


def save_portfolio_state(
    cash: float,
    positions: Iterable[dict] | None,
    *,
    base_dir: str | Path | None = None,
) -> dict:
    cash_value = _finite(cash)
    if cash_value is None or cash_value < 0:
        raise ValueError("Cash / unallocated capital must be zero or greater")

    state = {
        "schema_version": 1,
        "cash": float(cash_value),
        "positions": normalize_positions(positions),
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    root = _portfolio_dir(base_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "state.json"
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)
    return state


def load_portfolio_state(
    *,
    base_dir: str | Path | None = None,
) -> dict:
    path = _portfolio_dir(base_dir) / "state.json"
    if not path.exists():
        return {
            "schema_version": 1,
            "cash": 0.0,
            "positions": [],
            "updated_at_utc": None,
        }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {
            "schema_version": 1,
            "cash": max(0.0, float(raw.get("cash", 0.0) or 0.0)),
            "positions": normalize_positions(raw.get("positions", [])),
            "updated_at_utc": raw.get("updated_at_utc"),
        }
    except Exception:
        return {
            "schema_version": 1,
            "cash": 0.0,
            "positions": [],
            "updated_at_utc": None,
        }


def _primary_decision(snapshot: dict) -> dict | None:
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


def _ranking_map(base_ranking: dict) -> dict[str, dict]:
    return {
        str(row.get("ticker", "")).upper(): row
        for row in (base_ranking.get("ranked", []) or [])
        if row.get("ticker")
    }


def _last_close(frame: pd.DataFrame | None) -> float | None:
    if frame is None or getattr(frame, "empty", True) or "Close" not in frame.columns:
        return None
    close = frame["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    values = pd.to_numeric(close, errors="coerce").dropna()
    return float(values.iloc[-1]) if not values.empty else None


def _resolve_price(
    ticker: str,
    ranking_row: dict | None,
    *,
    period: str = "1mo",
) -> tuple[float | None, str]:
    try:
        frame = fetch_stock_data(ticker, period, "1d")
        price = _last_close(frame)
        if price is not None and price > 0:
            return price, str(frame.attrs.get("provider") or "market_data")
    except Exception:
        pass

    if ranking_row:
        reference = _finite(ranking_row.get("reference_entry"))
        if reference is not None and reference > 0:
            return reference, "decision_reference"
    return None, "unavailable"


def _decision_context(ticker: str, ranking_row: dict | None) -> dict:
    if ranking_row:
        return {
            "direction": str(ranking_row.get("direction", "NEUTRAL")).upper(),
            "recommendation": str(ranking_row.get("recommendation", "WAIT")).upper(),
            "invalidation": _finite(ranking_row.get("invalidation")),
            "decision_target": _finite(ranking_row.get("decision_target")),
            "horizon": int(ranking_row.get("horizon", 0) or 0),
        }

    snapshot = load_decision_snapshot(ticker)
    row = _primary_decision(snapshot) if snapshot else None
    if not row:
        return {
            "direction": "UNKNOWN",
            "recommendation": "UNAVAILABLE",
            "invalidation": None,
            "decision_target": None,
            "horizon": 0,
        }
    return {
        "direction": str(row.get("direction", "NEUTRAL")).upper(),
        "recommendation": str(row.get("recommendation", "WAIT")).upper(),
        "invalidation": _finite(row.get("invalidation")),
        "decision_target": _finite(row.get("decision_target")),
        "horizon": int(row.get("horizon", 0) or 0),
    }


def value_portfolio(
    portfolio_state: dict,
    *,
    base_ranking: dict | None = None,
) -> dict:
    positions = normalize_positions(portfolio_state.get("positions", []))
    cash = max(0.0, float(portfolio_state.get("cash", 0.0) or 0.0))
    ranking_map = _ranking_map(base_ranking or {})

    enriched = []
    gross_exposure = 0.0
    net_market_value = 0.0
    total_unrealized = 0.0

    for position in positions:
        ticker = position["ticker"]
        row = ranking_map.get(ticker)
        price, price_source = _resolve_price(ticker, row)
        quantity = float(position["quantity"])
        cost_basis = float(position["cost_basis"])
        side = "LONG" if quantity > 0 else "SHORT"

        if price is None:
            market_value = None
            gross_value = abs(quantity * cost_basis)
            unrealized = None
        else:
            market_value = quantity * price
            gross_value = abs(market_value)
            unrealized = (price - cost_basis) * quantity
            net_market_value += market_value
            total_unrealized += unrealized

        gross_exposure += gross_value
        context = _decision_context(ticker, row)
        invalidation = context["invalidation"]

        decision_direction = context["direction"]
        invalidation_applicable = (
            (side == "LONG" and decision_direction == "BULLISH")
            or (side == "SHORT" and decision_direction == "BEARISH")
        )
        invalidation_breached = False
        if invalidation_applicable and price is not None and invalidation is not None:
            if side == "LONG" and price <= invalidation:
                invalidation_breached = True
            elif side == "SHORT" and price >= invalidation:
                invalidation_breached = True

        enriched.append({
            **position,
            "side": side,
            "current_price": price,
            "price_source": price_source,
            "market_value": market_value,
            "gross_value": gross_value,
            "unrealized_pl": unrealized,
            "unrealized_pl_pct": None
            if price is None
            else float(((price / cost_basis) - 1.0) * 100.0 * (1 if quantity > 0 else -1)),
            "decision_direction": decision_direction,
            "decision_recommendation": context["recommendation"],
            "decision_horizon": context["horizon"],
            "invalidation": invalidation,
            "invalidation_applicable": invalidation_applicable,
            "decision_target": context["decision_target"],
            "invalidation_breached": invalidation_breached,
        })

    capital_base = cash + gross_exposure
    if capital_base <= 0:
        capital_base = 1.0

    for row in enriched:
        row["portfolio_weight_pct"] = float(row["gross_value"] / capital_base * 100.0)

    long_exposure = sum(row["gross_value"] for row in enriched if row["side"] == "LONG")
    short_exposure = sum(row["gross_value"] for row in enriched if row["side"] == "SHORT")

    return {
        "cash": cash,
        "capital_base": float(capital_base),
        "gross_exposure": float(gross_exposure),
        "net_market_value": float(net_market_value),
        "estimated_net_liquidation": float(cash + net_market_value),
        "total_unrealized_pl": float(total_unrealized),
        "cash_weight_pct": float(cash / capital_base * 100.0),
        "long_exposure_pct": float(long_exposure / capital_base * 100.0),
        "short_exposure_pct": float(short_exposure / capital_base * 100.0),
        "position_count": len(enriched),
        "positions": enriched,
    }


def _corr(matrix: dict, left: str, right: str) -> float | None:
    try:
        value = matrix.get(left, {}).get(right)
        if value is None:
            return None
        value = float(value)
        return value if np.isfinite(value) else None
    except Exception:
        return None


def _candidate_direction(row: dict) -> str:
    direction = str(row.get("direction_bucket") or "").upper()
    if direction in {"LONG", "SHORT"}:
        return direction
    recommendation = str(row.get("recommendation", "")).upper()
    if recommendation == "LONG_SETUP":
        return "LONG"
    if recommendation == "SHORT_SETUP":
        return "SHORT"
    raw = str(row.get("direction", "")).upper()
    return "LONG" if raw == "BULLISH" else ("SHORT" if raw == "BEARISH" else "NEUTRAL")


def build_portfolio_aware_ranking(
    base_ranking: dict | None = None,
    portfolio_state: dict | None = None,
    *,
    max_position_pct: float = 20.0,
    max_correlated_cluster_pct: float = 40.0,
    correlation_threshold: float = 0.70,
    include_portfolio_correlation: bool = True,
    correlation_period: str = "6mo",
) -> dict:
    base = base_ranking or load_ranking_snapshot()
    if not base:
        raise ValueError("No 3.4 opportunity ranking exists yet")

    state = portfolio_state or load_portfolio_state()
    valuation = value_portfolio(state, base_ranking=base)
    position_map = {
        row["ticker"]: row
        for row in valuation["positions"]
    }

    ranked = [dict(row) for row in (base.get("ranked", []) or [])]
    all_symbols = normalize_watchlist(
        [row.get("ticker", "") for row in ranked]
        + [row.get("ticker", "") for row in valuation["positions"]]
    )

    correlation_matrix = base.get("correlation_matrix") or {}
    correlation_rows = base.get("correlation_return_rows") or {}
    if include_portfolio_correlation and len(all_symbols) >= 2:
        try:
            correlation_matrix, correlation_rows = build_return_correlation(
                all_symbols,
                period=correlation_period,
            )
        except Exception:
            pass

    alerts = []
    for position in valuation["positions"]:
        if position["portfolio_weight_pct"] > float(max_position_pct):
            alerts.append({
                "type": "CONCENTRATION",
                "ticker": position["ticker"],
                "message": (
                    f"{position['ticker']} is {position['portfolio_weight_pct']:.1f}% "
                    f"of gross capital vs {max_position_pct:.1f}% single-name limit"
                ),
            })
        if position["invalidation_breached"]:
            alerts.append({
                "type": "INVALIDATION",
                "ticker": position["ticker"],
                "message": (
                    f"{position['ticker']} has crossed its latest governed "
                    f"decision invalidation level"
                ),
            })

    overlay = []
    for row in ranked:
        ticker = str(row.get("ticker", "")).upper()
        candidate_side = _candidate_direction(row)
        position = position_map.get(ticker)
        current_weight = float(position["portfolio_weight_pct"]) if position else 0.0

        same_side = bool(position and position["side"] == candidate_side and candidate_side != "NEUTRAL")
        opposite_side = bool(
            position
            and candidate_side in {"LONG", "SHORT"}
            and position["side"] != candidate_side
        )
        breached = bool(position and position.get("invalidation_breached"))

        correlated_exposure = 0.0
        correlated_positions = []
        if candidate_side != "NEUTRAL":
            for held in valuation["positions"]:
                if held["side"] != candidate_side:
                    continue
                corr = _corr(correlation_matrix, ticker, held["ticker"])
                if held["ticker"] == ticker:
                    corr = 1.0
                if corr is not None and corr >= float(correlation_threshold):
                    correlated_exposure += float(held["portfolio_weight_pct"])
                    correlated_positions.append({
                        "ticker": held["ticker"],
                        "correlation": float(corr),
                        "weight_pct": float(held["portfolio_weight_pct"]),
                    })

        if current_weight >= float(max_position_pct):
            concentration_multiplier = 0.10
        elif current_weight >= float(max_position_pct) * 0.75:
            concentration_multiplier = 0.50
        elif current_weight >= float(max_position_pct) * 0.50:
            concentration_multiplier = 0.75
        else:
            concentration_multiplier = 1.0

        cluster_ratio = correlated_exposure / max(float(max_correlated_cluster_pct), 1e-12)
        if cluster_ratio >= 1.0:
            cluster_multiplier = 0.20
        elif cluster_ratio >= 0.75:
            cluster_multiplier = 0.50
        elif cluster_ratio >= 0.50:
            cluster_multiplier = 0.75
        else:
            cluster_multiplier = 1.0

        conflict_multiplier = 0.0 if opposite_side else 1.0
        invalidation_multiplier = 0.0 if breached else 1.0

        ranking_score = float(row.get("ranking_score", 0.0) or 0.0)
        portfolio_score = (
            ranking_score
            * concentration_multiplier
            * cluster_multiplier
            * conflict_multiplier
            * invalidation_multiplier
        )

        single_headroom = max(0.0, float(max_position_pct) - current_weight)
        cluster_headroom = max(
            0.0,
            float(max_correlated_cluster_pct) - correlated_exposure,
        )
        base_budget = float(row.get("research_risk_budget_pct", 0.0) or 0.0)

        suggested_budget = 0.0
        if (
            bool(row.get("actionable"))
            and row.get("evidence_status") == "CALIBRATED"
            and not opposite_side
            and not breached
            and candidate_side in {"LONG", "SHORT"}
        ):
            suggested_budget = min(
                base_budget,
                single_headroom,
                cluster_headroom,
            )

        if breached:
            portfolio_action = "EXIT_REVIEW"
        elif opposite_side:
            portfolio_action = "POSITION_CONFLICT"
        elif position and same_side:
            if suggested_budget > 0:
                portfolio_action = "ADD_CANDIDATE"
            else:
                portfolio_action = "HOLD_MONITOR"
        elif position:
            portfolio_action = "HOLD_MONITOR"
        elif suggested_budget > 0 and candidate_side == "LONG":
            portfolio_action = "NEW_ENTRY_CANDIDATE"
        elif suggested_budget > 0 and candidate_side == "SHORT":
            portfolio_action = "NEW_SHORT_CANDIDATE"
        else:
            portfolio_action = "WATCH"

        enriched = dict(row)
        enriched.update({
            "current_position": bool(position),
            "current_position_side": None if not position else position["side"],
            "current_position_weight_pct": current_weight,
            "current_quantity": None if not position else position["quantity"],
            "current_cost_basis": None if not position else position["cost_basis"],
            "current_price": None if not position else position["current_price"],
            "unrealized_pl": None if not position else position["unrealized_pl"],
            "unrealized_pl_pct": None if not position else position["unrealized_pl_pct"],
            "candidate_side": candidate_side,
            "position_conflict": opposite_side,
            "invalidation_breached": breached,
            "correlated_existing_exposure_pct": float(correlated_exposure),
            "correlated_positions": correlated_positions,
            "single_name_headroom_pct": float(single_headroom),
            "correlated_cluster_headroom_pct": float(cluster_headroom),
            "concentration_multiplier": float(concentration_multiplier),
            "portfolio_correlation_multiplier": float(cluster_multiplier),
            "portfolio_ranking_score": float(portfolio_score),
            "portfolio_research_budget_pct": float(suggested_budget),
            "portfolio_action": portfolio_action,
        })
        overlay.append(enriched)

    overlay.sort(key=lambda row: row["portfolio_ranking_score"], reverse=True)
    for rank, row in enumerate(overlay, start=1):
        row["portfolio_rank"] = rank

    allocated = sum(float(row["portfolio_research_budget_pct"]) for row in overlay)
    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_ranking_generated_at_utc": base.get("generated_at_utc"),
        "portfolio_updated_at_utc": state.get("updated_at_utc"),
        "portfolio_summary": {
            key: value
            for key, value in valuation.items()
            if key != "positions"
        },
        "positions": valuation["positions"],
        "max_position_pct": float(max_position_pct),
        "max_correlated_cluster_pct": float(max_correlated_cluster_pct),
        "correlation_threshold": float(correlation_threshold),
        "correlation_matrix": correlation_matrix,
        "correlation_return_rows": correlation_rows,
        "alerts": alerts,
        "ranked": overlay,
        "allocated_portfolio_research_budget_pct": float(allocated),
        "unallocated_portfolio_research_budget_pct": float(max(0.0, 100.0 - allocated)),
        "notes": [
            "Portfolio-aware allocation can only reduce the 3.4 research risk budget; it never increases it.",
            "Existing concentration and correlated same-direction exposure reduce new research headroom.",
            "Opposite-side positions and breached governed invalidation levels receive zero new research budget.",
            "Portfolio actions are review labels only; v3.5 does not place, close, or resize trades automatically.",
            "Capital weights use cash plus gross absolute exposure so long and short positions can coexist without hiding leverage.",
        ],
    }
    persist_portfolio_overlay(result)
    return result


def persist_portfolio_overlay(
    result: dict,
    *,
    base_dir: str | Path | None = None,
) -> Path:
    root = _portfolio_dir(base_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "latest_overlay.json"
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    temp.replace(path)
    return path


def load_portfolio_overlay(
    *,
    base_dir: str | Path | None = None,
) -> dict:
    path = _portfolio_dir(base_dir) / "latest_overlay.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}
