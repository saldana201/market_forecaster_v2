"""Supabase Auth adapter using the provider's GoTrue REST API.

Passwords are sent only to Supabase Auth. Market Forecaster never stores or hashes
application passwords itself.
"""
from __future__ import annotations

import json
from urllib import error, request

from market_forecaster.auth.provider import (
    AuthConfigurationError,
    AuthProviderError,
    AuthResult,
    AuthTokens,
    AuthUser,
    InvalidCredentials,
    InvalidToken,
)


class SupabaseAuthProvider:
    name = "supabase"

    def __init__(self, url: str, anon_key: str, timeout_seconds: float = 10.0):
        self.url = str(url or "").strip().rstrip("/")
        self.anon_key = str(anon_key or "").strip()
        self.timeout_seconds = float(timeout_seconds)
        if not self.url or not self.anon_key:
            raise AuthConfigurationError("Supabase URL and anonymous key are required.")

    def _request(
        self,
        path: str,
        *,
        method: str,
        payload: dict | None = None,
        access_token: str | None = None,
    ) -> dict:
        headers = {
            "apikey": self.anon_key,
            "Content-Type": "application/json",
        }
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            message = body
            try:
                parsed = json.loads(body)
                message = (
                    parsed.get("msg")
                    or parsed.get("message")
                    or parsed.get("error_description")
                    or parsed.get("error")
                    or body
                )
            except Exception:
                pass
            if exc.code in {401, 403}:
                if access_token:
                    raise InvalidToken(str(message)) from exc
                raise InvalidCredentials(str(message)) from exc
            if exc.code == 400 and "invalid" in str(message).lower():
                raise InvalidCredentials(str(message)) from exc
            raise AuthProviderError(str(message)) from exc
        except error.URLError as exc:
            raise AuthProviderError(f"Authentication provider unavailable: {exc.reason}") from exc

    @staticmethod
    def _user(payload: dict | None) -> AuthUser:
        row = payload or {}
        subject = str(row.get("id") or "").strip()
        if not subject:
            raise AuthProviderError("Authentication provider returned no user subject.")
        metadata = row.get("user_metadata") or {}
        email_confirmed = bool(row.get("email_confirmed_at") or row.get("confirmed_at"))
        return AuthUser(
            subject=subject,
            email=row.get("email"),
            display_name=metadata.get("display_name") or metadata.get("name"),
            email_confirmed=email_confirmed,
        )

    @staticmethod
    def _tokens(payload: dict) -> AuthTokens | None:
        access = str(payload.get("access_token") or "").strip()
        if not access:
            return None
        return AuthTokens(
            access_token=access,
            refresh_token=payload.get("refresh_token"),
            expires_in=payload.get("expires_in"),
            token_type=str(payload.get("token_type") or "bearer"),
        )

    def register(self, email: str, password: str, display_name: str | None = None) -> AuthResult:
        payload: dict = {"email": email.strip(), "password": password}
        if display_name:
            payload["data"] = {"display_name": display_name.strip()}
        result = self._request("/auth/v1/signup", method="POST", payload=payload)
        user = self._user(result.get("user"))
        tokens = self._tokens(result)
        return AuthResult(
            user=user,
            tokens=tokens,
            requires_email_confirmation=tokens is None,
        )

    def login(self, email: str, password: str) -> AuthResult:
        result = self._request(
            "/auth/v1/token?grant_type=password",
            method="POST",
            payload={"email": email.strip(), "password": password},
        )
        return AuthResult(
            user=self._user(result.get("user")),
            tokens=self._tokens(result),
            requires_email_confirmation=False,
        )

    def logout(self, access_token: str) -> None:
        self._request("/auth/v1/logout", method="POST", access_token=access_token)

    def verify_token(self, access_token: str) -> AuthUser:
        result = self._request("/auth/v1/user", method="GET", access_token=access_token)
        return self._user(result)
