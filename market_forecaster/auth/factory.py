"""Authentication provider factory."""
from __future__ import annotations

import os

from market_forecaster.auth.provider import AuthConfigurationError, AuthProvider
from market_forecaster.auth.supabase import SupabaseAuthProvider
from market_forecaster.config import MULTI_USER_ENABLED


def auth_provider_name() -> str:
    return str(os.getenv("MARKET_FORECASTER_AUTH_PROVIDER", "supabase")).strip().lower()


def auth_configuration_status() -> tuple[bool, str]:
    if not MULTI_USER_ENABLED:
        return False, "MULTI_USER_ENABLED is false."

    provider = auth_provider_name()
    if provider != "supabase":
        return False, f"Unsupported auth provider: {provider}"

    url = os.getenv("MARKET_FORECASTER_SUPABASE_URL") or os.getenv("SUPABASE_URL")
    key = os.getenv("MARKET_FORECASTER_SUPABASE_ANON_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        return False, "Supabase URL or anonymous key is not configured."
    return True, "ready"


def get_auth_provider() -> AuthProvider:
    ready, reason = auth_configuration_status()
    if not ready:
        raise AuthConfigurationError(reason)

    provider = auth_provider_name()
    if provider == "supabase":
        return SupabaseAuthProvider(
            os.getenv("MARKET_FORECASTER_SUPABASE_URL") or os.getenv("SUPABASE_URL") or "",
            os.getenv("MARKET_FORECASTER_SUPABASE_ANON_KEY") or os.getenv("SUPABASE_ANON_KEY") or "",
        )
    raise AuthConfigurationError(f"Unsupported auth provider: {provider}")
