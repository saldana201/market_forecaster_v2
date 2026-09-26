"""Server-side persistent browser sessions for authenticated Streamlit users."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib import error, parse, request

from cryptography.fernet import Fernet, InvalidToken as FernetInvalidToken


class BrowserSessionError(RuntimeError):
    """Raised when the server-side browser-session store cannot be used."""


@dataclass(frozen=True)
class StoredBrowserSession:
    auth_subject: str
    refresh_token: str
    expires_at: datetime


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


def browser_session_configuration_status() -> tuple[bool, str]:
    if not _supabase_url():
        return False, "Supabase URL is not configured."
    if not _service_role_key():
        return False, "Supabase service-role key is not configured on the app host."
    return True, "ready"


def _fernet() -> Fernet:
    secret = _service_role_key()
    if not secret:
        raise BrowserSessionError("Browser-session encryption key is unavailable.")
    digest = hashlib.sha256(
        b"market-forecaster-browser-session-v1:" + secret.encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _hash_handle(handle: str) -> str:
    return hashlib.sha256(str(handle or "").encode("utf-8")).hexdigest()


def _hash_user_agent(user_agent: str) -> str:
    return hashlib.sha256(str(user_agent or "").encode("utf-8")).hexdigest()


def _request_rows(
    *,
    method: str,
    query: dict[str, str] | None = None,
    payload: object | None = None,
    prefer: str | None = None,
    timeout_seconds: float = 5.0,
) -> list[dict]:
    ready, reason = browser_session_configuration_status()
    if not ready:
        raise BrowserSessionError(reason)

    qs = parse.urlencode(query or {}, safe="(),.*:-")
    endpoint = f"{_supabase_url()}/rest/v1/browser_auth_sessions"
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
        raise BrowserSessionError(
            f"Persistent browser session request failed ({exc.code}): {body}"
        ) from exc
    except error.URLError as exc:
        raise BrowserSessionError(
            f"Persistent browser session store unavailable: {exc.reason}"
        ) from exc

    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        raise BrowserSessionError(
            "Persistent browser session store returned invalid JSON."
        ) from exc

    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return [parsed]
    return []


def create_browser_session(
    *,
    auth_subject: str,
    refresh_token: str,
    user_agent: str,
    ttl_days: int = 30,
) -> str:
    ready, reason = browser_session_configuration_status()
    if not ready:
        raise BrowserSessionError(reason)
    if not auth_subject or not refresh_token:
        raise BrowserSessionError("Verified subject and refresh token are required.")

    handle = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(days=max(1, int(ttl_days)))
    ciphertext = _fernet().encrypt(refresh_token.encode("utf-8")).decode("ascii")

    _request_rows(
        method="POST",
        payload={
            "handle_hash": _hash_handle(handle),
            "auth_subject": auth_subject,
            "refresh_token_ciphertext": ciphertext,
            "user_agent_hash": _hash_user_agent(user_agent),
            "expires_at": expires_at.isoformat(),
        },
        prefer="return=minimal",
    )
    return handle


def load_browser_session(
    *,
    handle: str,
    user_agent: str,
) -> StoredBrowserSession | None:
    if not handle:
        return None

    rows = _request_rows(
        method="GET",
        query={
            "select": (
                "auth_subject,refresh_token_ciphertext,user_agent_hash,"
                "expires_at,revoked_at"
            ),
            "handle_hash": f"eq.{_hash_handle(handle)}",
            "limit": "1",
        },
    )
    if not rows:
        return None

    row = rows[0]
    if row.get("revoked_at"):
        return None

    try:
        expires_at = datetime.fromisoformat(
            str(row.get("expires_at") or "").replace("Z", "+00:00")
        )
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
    except Exception:
        return None

    if expires_at <= datetime.now(timezone.utc):
        return None

    expected_ua = str(row.get("user_agent_hash") or "")
    actual_ua = _hash_user_agent(user_agent)
    if not hmac.compare_digest(expected_ua, actual_ua):
        return None

    try:
        refresh_token = _fernet().decrypt(
            str(row.get("refresh_token_ciphertext") or "").encode("ascii")
        ).decode("utf-8")
    except (FernetInvalidToken, ValueError, UnicodeDecodeError) as exc:
        raise BrowserSessionError(
            "Persistent browser session token could not be decrypted."
        ) from exc

    _request_rows(
        method="PATCH",
        query={"handle_hash": f"eq.{_hash_handle(handle)}"},
        payload={"last_seen_at": datetime.now(timezone.utc).isoformat()},
        prefer="return=minimal",
    )

    return StoredBrowserSession(
        auth_subject=str(row.get("auth_subject") or ""),
        refresh_token=refresh_token,
        expires_at=expires_at,
    )


def rotate_browser_refresh_token(*, handle: str, refresh_token: str) -> None:
    if not handle or not refresh_token:
        return
    ciphertext = _fernet().encrypt(refresh_token.encode("utf-8")).decode("ascii")
    _request_rows(
        method="PATCH",
        query={"handle_hash": f"eq.{_hash_handle(handle)}"},
        payload={
            "refresh_token_ciphertext": ciphertext,
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
        },
        prefer="return=minimal",
    )


def revoke_browser_session(handle: str) -> None:
    if not handle:
        return
    _request_rows(
        method="PATCH",
        query={"handle_hash": f"eq.{_hash_handle(handle)}"},
        payload={"revoked_at": datetime.now(timezone.utc).isoformat()},
        prefer="return=minimal",
    )
