"""Minimal Supabase Data API client using the authenticated user's JWT.

The publishable key identifies the application. The bearer token identifies the
signed-in user and allows Postgres RLS to enforce row ownership.
"""
from __future__ import annotations

import json
from urllib import error, parse, request


class PersistenceError(RuntimeError):
    """Raised when Supabase persistence cannot complete a request."""


class SupabaseDataClient:
    def __init__(
        self,
        url: str,
        publishable_key: str,
        access_token: str,
        timeout_seconds: float = 12.0,
    ):
        self.url = str(url or "").strip().rstrip("/")
        self.publishable_key = str(publishable_key or "").strip()
        self.access_token = str(access_token or "").strip()
        self.timeout_seconds = float(timeout_seconds)
        if not self.url or not self.publishable_key or not self.access_token:
            raise PersistenceError(
                "Supabase URL, publishable key, and authenticated access token are required."
            )

    def _request(
        self,
        table: str,
        *,
        method: str = "GET",
        query: dict[str, str] | None = None,
        payload: object | None = None,
        prefer: str | None = None,
    ) -> list[dict]:
        qs = parse.urlencode(query or {}, safe="(),.*:-")
        endpoint = f"{self.url}/rest/v1/{table}"
        if qs:
            endpoint += f"?{qs}"

        headers = {
            "apikey": self.publishable_key,
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer

        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = request.Request(endpoint, data=data, headers=headers, method=method)

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
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
            message = body
            try:
                parsed = json.loads(body)
                message = (
                    parsed.get("message")
                    or parsed.get("hint")
                    or parsed.get("details")
                    or parsed.get("code")
                    or body
                )
            except Exception:
                pass
            raise PersistenceError(f"Supabase Data API request failed: {message}") from exc
        except error.URLError as exc:
            raise PersistenceError(f"Supabase Data API unavailable: {exc.reason}") from exc

    def select(
        self,
        table: str,
        *,
        select: str = "*",
        filters: dict[str, str] | None = None,
        order: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        query = {"select": select}
        query.update(filters or {})
        if order:
            query["order"] = order
        if limit is not None:
            query["limit"] = str(int(limit))
        return self._request(table, query=query)

    def insert(
        self,
        table: str,
        rows: dict | list[dict],
        *,
        upsert: bool = False,
        on_conflict: str | None = None,
    ) -> list[dict]:
        query = {}
        if on_conflict:
            query["on_conflict"] = on_conflict
        prefer = "return=representation"
        if upsert:
            prefer = "resolution=merge-duplicates,return=representation"
        return self._request(
            table,
            method="POST",
            query=query,
            payload=rows,
            prefer=prefer,
        )

    def update(
        self,
        table: str,
        values: dict,
        *,
        filters: dict[str, str],
    ) -> list[dict]:
        return self._request(
            table,
            method="PATCH",
            query=filters,
            payload=values,
            prefer="return=representation",
        )

    def delete(self, table: str, *, filters: dict[str, str]) -> list[dict]:
        return self._request(
            table,
            method="DELETE",
            query=filters,
            prefer="return=representation",
        )
