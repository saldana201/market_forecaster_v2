from __future__ import annotations

from market_forecaster.core.session_identity import AppIdentity
from market_forecaster.persistence.supabase_data import PersistenceError
from market_forecaster.services.user_data import (
    add_watchlist_item,
    get_or_create_watchlist,
    save_primary_portfolio,
    verified_owner_id,
)


USER_A = "11111111-1111-4111-8111-111111111111"


def _identity(**overrides) -> AppIdentity:
    data = {
        "user_id": "spoofable-internal-display-id",
        "session_id": "session-1",
        "authenticated": True,
        "plan": "standard",
        "subscription_status": "bootstrap",
        "is_admin": False,
        "auth_provider": "supabase",
        "auth_subject": USER_A,
    }
    data.update(overrides)
    return AppIdentity(**data)


class FakeClient:
    def __init__(self):
        self.calls = []
        self.watchlist = None
        self.portfolio = None
        self.positions = []

    def select(self, table, **kwargs):
        self.calls.append(("select", table, kwargs))
        if table == "watchlists":
            return [] if self.watchlist is None else [self.watchlist]
        if table == "portfolios":
            return [] if self.portfolio is None else [self.portfolio]
        if table == "portfolio_positions":
            return list(self.positions)
        return []

    def insert(self, table, rows, **kwargs):
        self.calls.append(("insert", table, rows, kwargs))
        if table == "watchlists":
            self.watchlist = {"id": "watch-1", **rows}
            return [self.watchlist]
        if table == "watchlist_items":
            return [{"id": "item-1", **rows}]
        if table == "portfolios":
            self.portfolio = {"id": "portfolio-1", **rows}
            return [self.portfolio]
        if table == "portfolio_positions":
            ticker = rows["ticker"]
            self.positions = [p for p in self.positions if p["ticker"] != ticker]
            self.positions.append({"id": f"pos-{ticker}", **rows})
            return [self.positions[-1]]
        return [rows]

    def update(self, table, values, **kwargs):
        self.calls.append(("update", table, values, kwargs))
        if table == "portfolios" and self.portfolio is not None:
            self.portfolio.update(values)
            return [self.portfolio]
        return []

    def delete(self, table, **kwargs):
        self.calls.append(("delete", table, kwargs))
        if table == "portfolio_positions":
            ticker_filter = kwargs["filters"]["ticker"]
            ticker = ticker_filter.removeprefix("eq.")
            self.positions = [p for p in self.positions if p["ticker"] != ticker]
        return []


def test_verified_owner_id_uses_supabase_subject_not_internal_user_id():
    identity = _identity(user_id="attacker-controlled-looking-value")

    assert verified_owner_id(identity) == USER_A
    assert verified_owner_id(identity) != identity.user_id


def test_verified_owner_id_rejects_demo_and_non_supabase_identity():
    for identity in [
        _identity(authenticated=False),
        _identity(auth_provider="other"),
        _identity(auth_subject="not-a-uuid"),
    ]:
        try:
            verified_owner_id(identity)
            assert False, "Expected PersistenceError"
        except PersistenceError:
            pass


def test_watchlist_rows_are_owned_by_verified_subject():
    client = FakeClient()
    identity = _identity()

    watchlist = get_or_create_watchlist(client, identity)
    item = add_watchlist_item(client, identity, watchlist["id"], "aapl")

    assert watchlist["user_id"] == USER_A
    assert item["user_id"] == USER_A
    assert item["ticker"] == "AAPL"


def test_portfolio_save_upserts_and_removes_positions_using_verified_owner():
    client = FakeClient()
    identity = _identity()

    client.portfolio = {
        "id": "portfolio-1",
        "user_id": USER_A,
        "name": "Primary Portfolio",
        "cash": 0,
    }
    client.positions = [
        {
            "id": "pos-MSFT",
            "user_id": USER_A,
            "portfolio_id": "portfolio-1",
            "ticker": "MSFT",
            "quantity": 1,
            "avg_cost": 100,
        }
    ]

    result = save_primary_portfolio(
        client,
        identity,
        cash=5000,
        positions=[
            {"ticker": "AAPL", "quantity": 2, "avg_cost": 180},
        ],
    )

    assert result["cash"] == 5000
    assert [row["ticker"] for row in result["positions"]] == ["AAPL"]

    aapl_insert = [
        call for call in client.calls
        if call[0] == "insert" and call[1] == "portfolio_positions"
    ][0]
    assert aapl_insert[2]["user_id"] == USER_A

    deletes = [
        call for call in client.calls
        if call[0] == "delete" and call[1] == "portfolio_positions"
    ]
    assert deletes
    assert deletes[0][2]["filters"]["user_id"] == f"eq.{USER_A}"
