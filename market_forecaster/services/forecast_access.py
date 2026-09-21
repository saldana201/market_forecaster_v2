"""Forecast access boundary for shared cached contracts."""
from __future__ import annotations

from dataclasses import dataclass

from market_forecaster.core.demo_universe import is_demo_ticker
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
