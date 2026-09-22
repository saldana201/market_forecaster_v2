"""Normalized application identity for Demo and authenticated sessions."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import MutableMapping
from uuid import uuid4


DEMO_SESSION_KEY = "demo_session"
IDENTITY_SESSION_KEY = "app_identity"


@dataclass(frozen=True)
class AppIdentity:
    user_id: str | None
    session_id: str
    authenticated: bool
    plan: str
    subscription_status: str
    is_admin: bool = False
    auth_provider: str | None = None
    auth_subject: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def new_demo_identity_for_session(session_id: str) -> AppIdentity:
    return AppIdentity(
        user_id=None,
        session_id=str(session_id),
        authenticated=False,
        plan="demo",
        subscription_status="not_applicable",
        is_admin=False,
        auth_provider=None,
        auth_subject=None,
    )


def new_demo_identity() -> AppIdentity:
    return new_demo_identity_for_session(str(uuid4()))


def ensure_demo_session(state: MutableMapping) -> dict:
    session = state.get(DEMO_SESSION_KEY)
    if not isinstance(session, dict):
        identity = new_demo_identity()
        session = {
            "session_id": identity.session_id,
            "watchlist": [],
            "portfolio": {"cash": 0.0, "positions": []},
            "viewed_forecasts": [],
        }
        state[DEMO_SESSION_KEY] = session
        state[IDENTITY_SESSION_KEY] = identity.to_dict()
        return session

    session.setdefault("session_id", str(uuid4()))
    session.setdefault("watchlist", [])
    session.setdefault("portfolio", {"cash": 0.0, "positions": []})
    session.setdefault("viewed_forecasts", [])

    identity = state.get(IDENTITY_SESSION_KEY)
    if not isinstance(identity, dict):
        state[IDENTITY_SESSION_KEY] = new_demo_identity_for_session(
            str(session["session_id"])
        ).to_dict()
    return session


def resolve_identity(state: MutableMapping) -> AppIdentity:
    ensure_demo_session(state)
    raw = state.get(IDENTITY_SESSION_KEY) or {}
    return AppIdentity(
        user_id=raw.get("user_id"),
        session_id=str(raw.get("session_id") or state[DEMO_SESSION_KEY]["session_id"]),
        authenticated=bool(raw.get("authenticated", False)),
        plan=str(raw.get("plan") or "demo").lower(),
        subscription_status=str(raw.get("subscription_status") or "not_applicable"),
        is_admin=bool(raw.get("is_admin", False)),
        auth_provider=raw.get("auth_provider"),
        auth_subject=raw.get("auth_subject"),
    )
