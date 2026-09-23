"""Persistent user-data service backed by Supabase RLS."""
from __future__ import annotations

import os
from typing import MutableMapping
from uuid import UUID

from market_forecaster.auth.session import AUTH_PROFILE_KEY, AUTH_SESSION_KEY
from market_forecaster.config import DATABASE_PERSISTENCE_ENABLED
from market_forecaster.core.session_identity import AppIdentity
from market_forecaster.persistence.supabase_data import PersistenceError, SupabaseDataClient


def _supabase_url() -> str:
    return (
        os.getenv("MARKET_FORECASTER_SUPABASE_URL")
        or os.getenv("SUPABASE_URL")
        or ""
    ).strip()


def _publishable_key() -> str:
    return (
        os.getenv("MARKET_FORECASTER_SUPABASE_PUBLISHABLE_KEY")
        or os.getenv("SUPABASE_PUBLISHABLE_KEY")
        or os.getenv("MARKET_FORECASTER_SUPABASE_ANON_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or ""
    ).strip()


def persistence_configuration_status() -> tuple[bool, str]:
    if not DATABASE_PERSISTENCE_ENABLED:
        return False, "DATABASE_PERSISTENCE_ENABLED is false."
    if not _supabase_url() or not _publishable_key():
        return False, "Supabase URL or publishable key is not configured."
    return True, "ready"


def verified_owner_id(identity: AppIdentity) -> str:
    if not identity.authenticated or identity.auth_provider != "supabase":
        raise PersistenceError("Persistent user data requires a verified Supabase account.")
    subject = str(identity.auth_subject or "").strip()
    try:
        return str(UUID(subject))
    except Exception as exc:
        raise PersistenceError("Verified Supabase subject is not a valid UUID.") from exc


def client_for_state(
    state: MutableMapping,
    identity: AppIdentity,
) -> SupabaseDataClient:
    ready, reason = persistence_configuration_status()
    if not ready:
        raise PersistenceError(reason)
    verified_owner_id(identity)

    auth = state.get(AUTH_SESSION_KEY) or {}
    token = auth.get("access_token") if isinstance(auth, dict) else None
    if not token:
        raise PersistenceError("Authenticated session token is unavailable.")

    return SupabaseDataClient(
        _supabase_url(),
        _publishable_key(),
        str(token),
    )


def ensure_profile(
    client: SupabaseDataClient,
    identity: AppIdentity,
    profile: dict | None = None,
) -> dict:
    user_id = verified_owner_id(identity)
    display_name = str((profile or {}).get("display_name") or "").strip() or None
    rows = client.insert(
        "profiles",
        {"user_id": user_id, "display_name": display_name},
        upsert=True,
        on_conflict="user_id",
    )
    return rows[0] if rows else {"user_id": user_id, "display_name": display_name}


def get_or_create_watchlist(
    client: SupabaseDataClient,
    identity: AppIdentity,
    name: str = "My Watchlist",
) -> dict:
    user_id = verified_owner_id(identity)
    rows = client.select(
        "watchlists",
        filters={"user_id": f"eq.{user_id}", "name": f"eq.{name}"},
        limit=1,
    )
    if rows:
        return rows[0]
    created = client.insert(
        "watchlists",
        {"user_id": user_id, "name": name},
    )
    if not created:
        raise PersistenceError("Could not create watchlist.")
    return created[0]


def list_watchlist_items(
    client: SupabaseDataClient,
    identity: AppIdentity,
    watchlist_id: str,
) -> list[dict]:
    user_id = verified_owner_id(identity)
    return client.select(
        "watchlist_items",
        filters={
            "user_id": f"eq.{user_id}",
            "watchlist_id": f"eq.{watchlist_id}",
        },
        order="sort_order.asc,created_at.asc",
    )


def add_watchlist_item(
    client: SupabaseDataClient,
    identity: AppIdentity,
    watchlist_id: str,
    ticker: str,
    sort_order: int = 0,
) -> dict:
    user_id = verified_owner_id(identity)
    symbol = str(ticker or "").upper().strip()
    if not symbol:
        raise PersistenceError("Ticker is required.")
    rows = client.insert(
        "watchlist_items",
        {
            "user_id": user_id,
            "watchlist_id": watchlist_id,
            "ticker": symbol,
            "sort_order": int(sort_order),
        },
        upsert=True,
        on_conflict="watchlist_id,ticker",
    )
    return rows[0] if rows else {"ticker": symbol}


def remove_watchlist_item(
    client: SupabaseDataClient,
    identity: AppIdentity,
    watchlist_id: str,
    ticker: str,
) -> None:
    user_id = verified_owner_id(identity)
    client.delete(
        "watchlist_items",
        filters={
            "user_id": f"eq.{user_id}",
            "watchlist_id": f"eq.{watchlist_id}",
            "ticker": f"eq.{str(ticker).upper().strip()}",
        },
    )


def get_or_create_portfolio(
    client: SupabaseDataClient,
    identity: AppIdentity,
    name: str = "Primary Portfolio",
) -> dict:
    user_id = verified_owner_id(identity)
    rows = client.select(
        "portfolios",
        filters={"user_id": f"eq.{user_id}", "name": f"eq.{name}"},
        limit=1,
    )
    if rows:
        return rows[0]
    created = client.insert(
        "portfolios",
        {"user_id": user_id, "name": name, "currency": "USD", "cash": 0},
    )
    if not created:
        raise PersistenceError("Could not create portfolio.")
    return created[0]


def load_portfolio_positions(
    client: SupabaseDataClient,
    identity: AppIdentity,
    portfolio_id: str,
) -> list[dict]:
    user_id = verified_owner_id(identity)
    return client.select(
        "portfolio_positions",
        filters={
            "user_id": f"eq.{user_id}",
            "portfolio_id": f"eq.{portfolio_id}",
        },
        order="ticker.asc",
    )


def save_primary_portfolio(
    client: SupabaseDataClient,
    identity: AppIdentity,
    *,
    cash: float,
    positions: list[dict],
) -> dict:
    user_id = verified_owner_id(identity)
    portfolio = get_or_create_portfolio(client, identity)
    portfolio_id = str(portfolio["id"])

    client.update(
        "portfolios",
        {"cash": float(cash)},
        filters={"id": f"eq.{portfolio_id}", "user_id": f"eq.{user_id}"},
    )

    existing = load_portfolio_positions(client, identity, portfolio_id)
    existing_by_ticker = {str(row.get("ticker") or "").upper(): row for row in existing}
    requested: set[str] = set()

    for raw in positions:
        ticker = str(raw.get("ticker") or "").upper().strip()
        quantity = float(raw.get("quantity") or 0)
        avg_cost = float(raw.get("avg_cost") or raw.get("cost_basis") or 0)
        if not ticker:
            continue
        if quantity <= 0:
            raise PersistenceError(f"Quantity for {ticker} must be greater than zero.")
        if avg_cost < 0:
            raise PersistenceError(f"Average cost for {ticker} cannot be negative.")
        requested.add(ticker)
        client.insert(
            "portfolio_positions",
            {
                "user_id": user_id,
                "portfolio_id": portfolio_id,
                "ticker": ticker,
                "quantity": quantity,
                "avg_cost": avg_cost,
            },
            upsert=True,
            on_conflict="portfolio_id,ticker",
        )

    for ticker in set(existing_by_ticker) - requested:
        client.delete(
            "portfolio_positions",
            filters={
                "user_id": f"eq.{user_id}",
                "portfolio_id": f"eq.{portfolio_id}",
                "ticker": f"eq.{ticker}",
            },
        )

    return {
        "id": portfolio_id,
        "cash": float(cash),
        "positions": load_portfolio_positions(client, identity, portfolio_id),
    }


def ensure_account_foundation(
    state: MutableMapping,
    identity: AppIdentity,
) -> tuple[SupabaseDataClient, dict]:
    client = client_for_state(state, identity)
    raw_profile = state.get(AUTH_PROFILE_KEY)
    profile = raw_profile if isinstance(raw_profile, dict) else {}
    stored_profile = ensure_profile(client, identity, profile)
    return client, stored_profile
