"""Forecast access boundary for shared cached contracts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from market_forecaster.config import SHARED_CONTRACT_STORAGE_ENABLED
from market_forecaster.core.demo_universe import demo_symbols, is_demo_ticker
from market_forecaster.core.research_snapshots import load_latest_contract
from market_forecaster.core.session_identity import AppIdentity
from market_forecaster.services.shared_contract_store import (
    SharedContractStoreError,
    load_shared_contract,
    load_shared_contracts,
)


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




def _load_best_contract(ticker: str, *, repo_root=None) -> tuple[dict | None, str]:
    symbol = str(ticker or "").upper().strip()
    if SHARED_CONTRACT_STORAGE_ENABLED:
        try:
            shared = load_shared_contract(symbol)
            if shared:
                return shared, "shared_supabase"
        except SharedContractStoreError:
            # Production remains readable if the shared store has a transient
            # outage and a deployment-local contract is available.
            pass

    local = load_latest_contract(symbol, repo_root=repo_root)
    return local, "local_cache" if local else "unavailable"


def load_demo_forecast(
    ticker: str,
    *,
    repo_root=None,
) -> ForecastAccessResult:
    symbol = str(ticker or "").upper().strip()
    if not is_demo_ticker(symbol):
        raise TickerNotEntitled(f"{symbol or 'Ticker'} is not available in Demo.")
    contract, source = _load_best_contract(symbol, repo_root=repo_root)
    if not contract:
        raise CachedForecastUnavailable(
            f"No cached Demo Forecast Contract is available for {symbol}."
        )
    return ForecastAccessResult(contract=contract, source=source)


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
    contract, source = _load_best_contract(
        str(ticker or "").upper().strip(),
        repo_root=repo_root,
    )
    if not contract:
        raise CachedForecastUnavailable("No cached Forecast Contract is available.")
    return ForecastAccessResult(contract=contract, source=source)


def demo_cache_status(*, repo_root=None) -> list[dict]:
    """Return lightweight readiness metadata for every enabled Demo symbol."""
    now = datetime.now(timezone.utc)
    symbols = demo_symbols()
    shared_contracts: dict[str, dict] = {}
    if SHARED_CONTRACT_STORAGE_ENABLED:
        try:
            shared_contracts = load_shared_contracts([row.ticker for row in symbols])
        except SharedContractStoreError:
            shared_contracts = {}

    rows: list[dict] = []
    for symbol in symbols:
        contract = shared_contracts.get(symbol.ticker)
        source = "shared_supabase" if contract else "local_cache"
        if not contract:
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
            "source": source if contract else "unavailable",
            "generated_at": generated_at,
            "as_of": contract.get("as_of") if contract else None,
            "contract_id": contract.get("contract_id") if contract else None,
            "current_price": contract.get("current_price") if contract else None,
            "forecasts": contract.get("forecasts", []) if contract else [],
            "age_hours": age_hours,
        })
    return rows
