"""Forecast access boundary for shared cached contracts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from market_forecaster.core.demo_universe import demo_symbols, is_demo_ticker
from market_forecaster.core.research_snapshots import load_latest_contract
from market_forecaster.core.session_identity import AppIdentity


class ForecastAccessError(RuntimeError):
    pass


class TickerNotEntitled(ForecastAccessError):
    pass


class CachedForecastUnavailable(ForecastAccessError):
    pass


@dataclass(frozen=True)
class ForecastAccessResult:
    contract: dict
    source: str = "shared_cache"


def load_demo_forecast(
    ticker: str,
    *,
    repo_root=None,
) -> ForecastAccessResult:
    symbol = str(ticker or "").upper().strip()
    if not is_demo_ticker(symbol):
        raise TickerNotEntitled(f"{symbol or 'Ticker'} is not available in Demo.")
    contract = load_latest_contract(symbol, repo_root=repo_root)
    if not contract:
        raise CachedForecastUnavailable(
            f"No cached Demo Forecast Contract is available for {symbol}."
        )
    return ForecastAccessResult(contract=contract)


def get_forecast_for_identity(
    identity: AppIdentity,
    ticker: str,
    *,
    repo_root=None,
) -> ForecastAccessResult:
    if identity.plan == "demo" and not identity.authenticated:
        return load_demo_forecast(ticker, repo_root=repo_root)

    # 4.1.0 intentionally does not add paid-user generation/authentication.
    # Existing internal tools continue to own generation until later phases.
    contract = load_latest_contract(str(ticker or "").upper().strip(), repo_root=repo_root)
    if not contract:
        raise CachedForecastUnavailable("No cached Forecast Contract is available.")
    return ForecastAccessResult(contract=contract)


def demo_cache_status(*, repo_root=None) -> list[dict]:
    """Return lightweight readiness metadata for every enabled Demo symbol."""
    now = datetime.now(timezone.utc)
    rows: list[dict] = []
    for symbol in demo_symbols():
        contract = load_latest_contract(symbol.ticker, repo_root=repo_root)
        generated_at = contract.get("generated_at") if contract else None
        age_hours = None
        if generated_at:
            try:
                stamp = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                age_hours = max(0.0, (now - stamp.astimezone(timezone.utc)).total_seconds() / 3600.0)
            except Exception:
                age_hours = None
        rows.append({
            "ticker": symbol.ticker,
            "display_name": symbol.display_name,
            "category": symbol.category,
            "asset_type": symbol.asset_type,
            "available": bool(contract),
            "generated_at": generated_at,
            "as_of": contract.get("as_of") if contract else None,
            "contract_id": contract.get("contract_id") if contract else None,
            "current_price": contract.get("current_price") if contract else None,
            "forecasts": contract.get("forecasts", []) if contract else [],
            "age_hours": age_hours,
        })
    return rows
