"""Durable shared Forecast Contract store for multi-instance deployments."""
from __future__ import annotations

import json
import os
from urllib import error, parse, request

from market_forecaster.config import SHARED_CONTRACT_STORAGE_ENABLED


class SharedContractStoreError(RuntimeError):
    """Raised when the shared Forecast Contract store cannot complete a request."""


def _supabase_url() -> str:
    return str(
        os.getenv("MARKET_FORECASTER_SUPABASE_URL")
        or os.getenv("SUPABASE_URL")
        or ""
    ).strip().rstrip("/")


def _publishable_key() -> str:
    return str(
        os.getenv("MARKET_FORECASTER_SUPABASE_PUBLISHABLE_KEY")
        or os.getenv("SUPABASE_PUBLISHABLE_KEY")
        or os.getenv("MARKET_FORECASTER_SUPABASE_ANON_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or ""
    ).strip()


def _service_role_key() -> str:
    return str(
        os.getenv("MARKET_FORECASTER_SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    ).strip()


def shared_read_configuration_status() -> tuple[bool, str]:
    if not SHARED_CONTRACT_STORAGE_ENABLED:
        return False, "SHARED_CONTRACT_STORAGE_ENABLED is false."
    if not _supabase_url():
        return False, "Supabase URL is not configured."
    if not (_publishable_key() or _service_role_key()):
        return False, "Supabase publishable/read key is not configured."
    return True, "ready"


def shared_write_configuration_status() -> tuple[bool, str]:
    if not SHARED_CONTRACT_STORAGE_ENABLED:
        return False, "SHARED_CONTRACT_STORAGE_ENABLED is false."
    if not _supabase_url():
        return False, "Supabase URL is not configured."
    if not _service_role_key():
        return False, "Supabase service-role key is not configured for publishing."
    return True, "ready"


def _request_rows(
    *,
    method: str,
    query: dict[str, str] | None = None,
    payload: object | None = None,
    write: bool = False,
    prefer: str | None = None,
) -> list[dict]:
    key = _service_role_key() if write else (_publishable_key() or _service_role_key())
    if not _supabase_url() or not key:
        raise SharedContractStoreError("Shared Forecast Contract store is not configured.")

    qs = parse.urlencode(query or {}, safe="(),.*:-")
    endpoint = f"{_supabase_url()}/rest/v1/shared_forecast_contracts"
    if qs:
        endpoint += f"?{qs}"

    headers = {
        "apikey": key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if write:
        headers["Authorization"] = f"Bearer {key}"
    if prefer:
        headers["Prefer"] = prefer

    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(endpoint, data=data, headers=headers, method=method)

    try:
        with request.urlopen(req, timeout=15.0) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return []
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return [parsed]
            return []
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SharedContractStoreError(
            f"Shared Forecast Contract request failed ({exc.code}): {body}"
        ) from exc
    except error.URLError as exc:
        raise SharedContractStoreError(
            f"Shared Forecast Contract store unavailable: {exc.reason}"
        ) from exc


def load_shared_contracts(tickers: list[str]) -> dict[str, dict]:
    ready, reason = shared_read_configuration_status()
    if not ready:
        raise SharedContractStoreError(reason)

    symbols = sorted({
        str(ticker or "").upper().strip()
        for ticker in tickers
        if str(ticker or "").strip()
    })
    if not symbols:
        return {}

    in_filter = "in.(" + ",".join(symbols) + ")"
    rows = _request_rows(
        method="GET",
        query={
            "select": "ticker,contract",
            "ticker": in_filter,
        },
    )
    result: dict[str, dict] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").upper().strip()
        contract = row.get("contract")
        if ticker and isinstance(contract, dict):
            result[ticker] = contract
    return result


def load_shared_contract(ticker: str) -> dict | None:
    symbol = str(ticker or "").upper().strip()
    return load_shared_contracts([symbol]).get(symbol)


def publish_shared_contract(contract: dict) -> dict:
    ready, reason = shared_write_configuration_status()
    if not ready:
        raise SharedContractStoreError(reason)

    ticker = str(contract.get("ticker") or "").upper().strip()
    contract_id = str(contract.get("contract_id") or "").strip()
    generated_at = str(contract.get("generated_at") or "").strip()
    if not ticker or not contract_id or not generated_at:
        raise SharedContractStoreError(
            "Contract ticker, contract_id, and generated_at are required."
        )

    rows = _request_rows(
        method="POST",
        query={"on_conflict": "ticker"},
        payload={
            "ticker": ticker,
            "contract_id": contract_id,
            "generated_at": generated_at,
            "as_of": contract.get("as_of"),
            "status": str(contract.get("status") or "UNAVAILABLE"),
            "schema_version": contract.get("schema_version"),
            "contract": contract,
        },
        write=True,
        prefer="resolution=merge-duplicates,return=representation",
    )
    return rows[0] if rows else {"ticker": ticker, "contract_id": contract_id}
