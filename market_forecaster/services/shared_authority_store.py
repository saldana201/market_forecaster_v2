"""Durable shared Forecast Authority store for multi-instance production."""
from __future__ import annotations

import json
import os
from urllib import error, parse, request

from market_forecaster.config import SHARED_AUTHORITY_ENABLED


class SharedAuthorityStoreError(RuntimeError):
    """Raised when the shared Forecast Authority store cannot complete a request."""


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


def shared_authority_read_configuration_status() -> tuple[bool, str]:
    if not SHARED_AUTHORITY_ENABLED:
        return False, "SHARED_AUTHORITY_ENABLED is false."
    if not _supabase_url():
        return False, "Supabase URL is not configured."
    if not (_publishable_key() or _service_role_key()):
        return False, "Supabase publishable/read key is not configured."
    return True, "ready"


def shared_authority_write_configuration_status() -> tuple[bool, str]:
    if not SHARED_AUTHORITY_ENABLED:
        return False, "SHARED_AUTHORITY_ENABLED is false."
    if not _supabase_url():
        return False, "Supabase URL is not configured."
    if not _service_role_key():
        return False, "Trusted Supabase service-role credential is not configured."
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
        raise SharedAuthorityStoreError("Shared Forecast Authority store is not configured.")

    qs = parse.urlencode(query or {}, safe="(),.*:-")
    endpoint = f"{_supabase_url()}/rest/v1/shared_forecast_authority"
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
        with request.urlopen(req, timeout=12.0) as response:
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
        raise SharedAuthorityStoreError(
            f"Shared Forecast Authority request failed ({exc.code}): {body}"
        ) from exc
    except error.URLError as exc:
        raise SharedAuthorityStoreError(
            f"Shared Forecast Authority store unavailable: {exc.reason}"
        ) from exc


def load_shared_authority() -> dict | None:
    ready, reason = shared_authority_read_configuration_status()
    if not ready:
        raise SharedAuthorityStoreError(reason)

    rows = _request_rows(
        method="GET",
        query={
            "select": "config,revision,updated_at",
            "authority_key": "eq.active",
            "limit": "1",
        },
    )
    if not rows:
        return None
    config = rows[0].get("config")
    return config if isinstance(config, dict) else None


def publish_shared_authority(config: dict) -> dict:
    ready, reason = shared_authority_write_configuration_status()
    if not ready:
        raise SharedAuthorityStoreError(reason)

    current = _request_rows(
        method="GET",
        query={
            "select": "revision",
            "authority_key": "eq.active",
            "limit": "1",
        },
        write=True,
    )
    revision = int(current[0].get("revision") or 0) + 1 if current else 1

    rows = _request_rows(
        method="POST",
        query={"on_conflict": "authority_key"},
        payload={
            "authority_key": "active",
            "schema_version": str(config.get("schema_version") or ""),
            "config": config,
            "revision": revision,
        },
        write=True,
        prefer="resolution=merge-duplicates,return=representation",
    )
    return rows[0] if rows else {"authority_key": "active", "revision": revision}
