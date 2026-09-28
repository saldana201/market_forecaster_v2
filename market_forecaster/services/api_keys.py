"""Service-role-only customer API key management for Pro accounts."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib import error, parse, request

from market_forecaster.config import SUBSCRIPTIONS_ENABLED
from market_forecaster.core.entitlements import can_use_api
from market_forecaster.core.session_identity import AppIdentity
from market_forecaster.services.subscriptions import ENTITLED_STATUSES
from market_forecaster.services.user_data import verified_owner_id


class APIKeyStoreError(RuntimeError):
    """Raised when customer API key storage/authorization is unavailable."""


class InvalidCustomerAPIKey(APIKeyStoreError):
    """Raised when a customer API key is unknown, revoked, or not entitled."""


@dataclass(frozen=True)
class APIKeyPrincipal:
    key_id: str
    user_id: str
    key_prefix: str
    plan: str
    subscription_status: str


def _supabase_url() -> str:
    return str(
        os.getenv("MARKET_FORECASTER_SUPABASE_URL")
        or os.getenv("SUPABASE_URL")
        or ""
    ).strip().rstrip("/")


def _service_role_key() -> str:
    return str(
        os.getenv("MARKET_FORECASTER_SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    ).strip()


def api_key_store_configuration_status() -> tuple[bool, str]:
    if not _supabase_url():
        return False, "Supabase URL is not configured."
    if not _service_role_key():
        return False, "Supabase service-role key is not configured on the app/API host."
    return True, "ready"


def _hash_api_key(api_key: str) -> str:
    return hashlib.sha256(str(api_key or "").encode("utf-8")).hexdigest()


def _request_rows(
    table: str,
    *,
    method: str = "GET",
    query: dict[str, str] | None = None,
    payload: object | None = None,
    prefer: str | None = None,
    timeout_seconds: float = 5.0,
) -> list[dict]:
    ready, reason = api_key_store_configuration_status()
    if not ready:
        raise APIKeyStoreError(reason)

    qs = parse.urlencode(query or {}, safe="(),.*:-")
    endpoint = f"{_supabase_url()}/rest/v1/{table}"
    if qs:
        endpoint += f"?{qs}"

    key = _service_role_key()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer

    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(endpoint, data=data, headers=headers, method=method)

    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise APIKeyStoreError(
            f"Customer API key store request failed ({exc.code}): {body}"
        ) from exc
    except error.URLError as exc:
        raise APIKeyStoreError(
            f"Customer API key store unavailable: {exc.reason}"
        ) from exc

    if not raw:
        return []

    try:
        parsed = json.loads(raw)
    except Exception as exc:
        raise APIKeyStoreError(
            "Customer API key store returned invalid JSON."
        ) from exc

    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return [parsed]
    return []


def list_user_api_keys(
    identity: AppIdentity,
    *,
    include_revoked: bool = False,
) -> list[dict]:
    user_id = verified_owner_id(identity)
    query = {
        "select": "id,name,key_prefix,created_at,last_used_at,revoked_at",
        "user_id": f"eq.{user_id}",
        "order": "created_at.desc",
        "limit": "50",
    }
    if not include_revoked:
        query["revoked_at"] = "is.null"
    return _request_rows("user_api_keys", query=query)


def create_user_api_key(
    identity: AppIdentity,
    *,
    name: str,
    max_active_keys: int = 5,
) -> dict:
    if not can_use_api(identity):
        raise APIKeyStoreError("Active Pro access is required to create API keys.")

    label = str(name or "").strip()
    if not label:
        raise APIKeyStoreError("API key name is required.")
    if len(label) > 80:
        raise APIKeyStoreError("API key name must be 80 characters or fewer.")

    active = list_user_api_keys(identity)
    if len(active) >= max(1, int(max_active_keys)):
        raise APIKeyStoreError(
            f"At most {max(1, int(max_active_keys))} active API keys are allowed per account."
        )

    user_id = verified_owner_id(identity)
    plaintext = "mfk_" + secrets.token_urlsafe(32)
    prefix = plaintext[:16]
    rows = _request_rows(
        "user_api_keys",
        method="POST",
        payload={
            "user_id": user_id,
            "name": label,
            "key_prefix": prefix,
            "key_hash": _hash_api_key(plaintext),
        },
        prefer="return=representation",
    )
    if not rows:
        raise APIKeyStoreError("Customer API key could not be created.")

    row = rows[0]
    return {
        "id": row.get("id"),
        "name": row.get("name") or label,
        "key_prefix": row.get("key_prefix") or prefix,
        "created_at": row.get("created_at"),
        "api_key": plaintext,
    }


def revoke_user_api_key(identity: AppIdentity, key_id: str) -> None:
    user_id = verified_owner_id(identity)
    key_id = str(key_id or "").strip()
    if not key_id:
        raise APIKeyStoreError("API key ID is required.")

    _request_rows(
        "user_api_keys",
        method="PATCH",
        query={
            "id": f"eq.{key_id}",
            "user_id": f"eq.{user_id}",
            "revoked_at": "is.null",
        },
        payload={"revoked_at": datetime.now(timezone.utc).isoformat()},
        prefer="return=minimal",
    )


def validate_customer_api_key(api_key: str) -> APIKeyPrincipal:
    if not SUBSCRIPTIONS_ENABLED:
        raise InvalidCustomerAPIKey("Customer API access is not enabled.")

    api_key = str(api_key or "").strip()
    if not api_key.startswith("mfk_") or len(api_key) < 30:
        raise InvalidCustomerAPIKey("Invalid customer API key.")

    rows = _request_rows(
        "user_api_keys",
        query={
            "select": "id,user_id,key_prefix,revoked_at",
            "key_hash": f"eq.{_hash_api_key(api_key)}",
            "revoked_at": "is.null",
            "limit": "1",
        },
    )
    if not rows:
        raise InvalidCustomerAPIKey("Invalid customer API key.")

    row = rows[0]
    user_id = str(row.get("user_id") or "").strip()
    key_id = str(row.get("id") or "").strip()
    if not user_id or not key_id:
        raise InvalidCustomerAPIKey("Invalid customer API key.")

    subscriptions = _request_rows(
        "subscriptions",
        query={
            "select": "plan,status",
            "user_id": f"eq.{user_id}",
            "limit": "1",
        },
    )
    subscription = subscriptions[0] if subscriptions else {}
    plan = str(subscription.get("plan") or "demo").lower()
    status = str(subscription.get("status") or "none").lower()

    if plan != "pro" or status not in ENTITLED_STATUSES:
        raise InvalidCustomerAPIKey("Active Pro subscription is required for API access.")

    try:
        _request_rows(
            "user_api_keys",
            method="PATCH",
            query={"id": f"eq.{key_id}"},
            payload={"last_used_at": datetime.now(timezone.utc).isoformat()},
            prefer="return=minimal",
            timeout_seconds=2.0,
        )
    except APIKeyStoreError:
        # Usage metadata is non-authoritative. Do not reject an otherwise valid
        # Pro request solely because the last-used timestamp could not be saved.
        pass

    return APIKeyPrincipal(
        key_id=key_id,
        user_id=user_id,
        key_prefix=str(row.get("key_prefix") or ""),
        plan=plan,
        subscription_status=status,
    )
