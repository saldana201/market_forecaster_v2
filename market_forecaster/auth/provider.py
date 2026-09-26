"""Provider-neutral authentication contracts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class AuthProviderError(RuntimeError):
    """Base managed-auth error."""


class AuthConfigurationError(AuthProviderError):
    """Raised when the configured provider is missing required settings."""


class InvalidCredentials(AuthProviderError):
    """Raised when sign-in credentials are rejected."""


class InvalidToken(AuthProviderError):
    """Raised when an access token is expired, malformed, or rejected."""


class RateLimited(AuthProviderError):
    """Raised when the managed auth provider applies a temporary cooldown."""

    def __init__(self, message: str, retry_after_seconds: int | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class AuthUser:
    subject: str
    email: str | None = None
    display_name: str | None = None
    email_confirmed: bool = False
    requested_plan: str | None = None


@dataclass(frozen=True)
class AuthTokens:
    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None
    token_type: str = "bearer"


@dataclass(frozen=True)
class AuthResult:
    user: AuthUser
    tokens: AuthTokens | None
    requires_email_confirmation: bool = False


class AuthProvider(Protocol):
    """Minimal adapter implemented by any managed identity provider."""

    name: str

    def register(
        self,
        email: str,
        password: str,
        display_name: str | None = None,
        requested_plan: str | None = None,
    ) -> AuthResult:
        ...

    def login(self, email: str, password: str) -> AuthResult:
        ...

    def refresh_session(self, refresh_token: str) -> AuthResult:
        ...

    def resend_confirmation(self, email: str) -> None:
        ...

    def update_password(self, access_token: str, new_password: str) -> AuthUser:
        ...

    def logout(self, access_token: str) -> None:
        ...

    def verify_token(self, access_token: str) -> AuthUser:
        ...
