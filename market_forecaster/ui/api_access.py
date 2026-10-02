"""Pro API key management UI."""
from __future__ import annotations

import json
import os
from urllib import error, request

import streamlit as st

from market_forecaster.core.entitlements import can_use_api
from market_forecaster.core.session_identity import resolve_identity
from market_forecaster.services.api_keys import (
    APIKeyStoreError,
    api_key_store_configuration_status,
    create_user_api_key,
    get_user_api_usage,
    list_user_api_keys,
    revoke_user_api_key,
)
from market_forecaster.ui.design_system import render_section_header


def _api_public_url() -> str:
    return str(os.getenv("MARKET_FORECASTER_API_PUBLIC_URL") or "").strip().rstrip("/")


def _pro_api_monthly_limit() -> int:
    try:
        return max(
            1,
            int(os.getenv("MARKET_FORECASTER_PRO_API_MONTHLY_REQUESTS", "1000")),
        )
    except (TypeError, ValueError):
        return 1000


def _test_customer_api_key(
    api_url: str,
    api_key: str,
    *,
    timeout_seconds: float = 8.0,
) -> dict:
    base = str(api_url or "").strip().rstrip("/")
    key = str(api_key or "").strip()
    if not base:
        raise APIKeyStoreError("Dedicated API hostname is not configured.")
    if not key:
        raise APIKeyStoreError("API key is missing.")

    req = request.Request(
        f"{base}/api/v1/api/usage",
        headers={
            "X-API-Key": key,
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise APIKeyStoreError(
            f"API connection test failed ({exc.code}): {body}"
        ) from exc
    except error.URLError as exc:
        raise APIKeyStoreError(
            f"API connection test could not reach the dedicated host: {exc.reason}"
        ) from exc

    try:
        payload = json.loads(raw)
    except Exception as exc:
        raise APIKeyStoreError(
            "API connection test returned invalid JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise APIKeyStoreError("API connection test returned an unexpected response.")
    return payload


def _short_timestamp(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Never"
    return raw.replace("T", " ")[:19] + (" UTC" if "Z" in raw or "+" in raw else "")


def render_api_access_panel() -> None:
    identity = resolve_identity(st.session_state)
    if not identity.authenticated:
        return

    render_section_header(
        "API Access",
        "Create individually revocable keys for programmatic access to protected Market Forecaster API routes.",
        badge="Pro",
    )

    with st.container(border=True):
        if not can_use_api(identity):
            st.info(
                "Customer API access is available with an active Pro subscription. "
                "Standard keeps the full Forecast Contract experience in the app, but does not issue API keys."
            )
            return

        ready, reason = api_key_store_configuration_status()
        if not ready:
            st.warning(f"API key management is temporarily unavailable: {reason}")
            return

        created = st.session_state.get("new_customer_api_key_once")
        if isinstance(created, dict) and created.get("api_key"):
            st.warning(
                "Copy this API key now. Market Forecaster stores only a hash and cannot show the full key again."
            )
            st.code(str(created["api_key"]), language="text")
            st.caption(
                f"Key name: {created.get('name') or 'API key'} · "
                f"Prefix: {created.get('key_prefix') or '—'}"
            )

            api_url = _api_public_url()
            if api_url:
                test_col, docs_col = st.columns(2)
                with test_col:
                    if st.button(
                        "Test API key",
                        key="api_key_test_once",
                        type="primary",
                        use_container_width=True,
                    ):
                        try:
                            result = _test_customer_api_key(
                                api_url,
                                str(created["api_key"]),
                            )
                            st.session_state["customer_api_test_result"] = result
                        except APIKeyStoreError as exc:
                            st.error(str(exc))
                with docs_col:
                    st.link_button(
                        "Open API docs",
                        f"{api_url}/docs",
                        use_container_width=True,
                    )

                test_result = st.session_state.get("customer_api_test_result")
                if isinstance(test_result, dict):
                    st.success(
                        "API key verified against the dedicated Pro API host."
                    )
                    result_col1, result_col2, result_col3 = st.columns(3)
                    with result_col1:
                        st.metric(
                            "Used",
                            f"{int(test_result.get('used') or 0):,}",
                        )
                    with result_col2:
                        st.metric(
                            "Remaining",
                            f"{int(test_result.get('remaining') or 0):,}",
                        )
                    with result_col3:
                        st.metric(
                            "Monthly limit",
                            f"{int(test_result.get('monthly_limit') or 0):,}",
                        )
                    st.caption(
                        "The connection test itself counts as one API request."
                    )

            if st.button(
                "I've saved this key",
                key="api_key_acknowledge_once",
                use_container_width=True,
            ):
                st.session_state.pop("new_customer_api_key_once", None)
                st.session_state.pop("customer_api_test_result", None)
                st.rerun()

        try:
            rows = list_user_api_keys(identity)
        except APIKeyStoreError as exc:
            st.error(f"Could not load API keys: {exc}")
            return

        active_count = len(rows)
        st.caption(
            f"{active_count} active API key{'s' if active_count != 1 else ''} · "
            "maximum 5 active keys per account"
        )

        try:
            usage = get_user_api_usage(
                identity,
                monthly_limit=_pro_api_monthly_limit(),
            )
        except APIKeyStoreError:
            usage = None

        if isinstance(usage, dict):
            used = int(usage.get("used") or 0)
            monthly_limit = int(usage.get("monthly_limit") or 0)
            remaining = int(usage.get("remaining") or 0)
            used_pct = (
                min(1.0, used / monthly_limit)
                if monthly_limit > 0
                else 0.0
            )
            usage_col, remaining_col = st.columns(2)
            with usage_col:
                st.metric(
                    "API requests this month",
                    f"{used:,} / {monthly_limit:,}",
                )
            with remaining_col:
                st.metric("Requests remaining", f"{remaining:,}")
            st.progress(used_pct)
            st.caption(
                "Included Pro API usage resets monthly. This quota is separate from "
                "the shorter per-minute abuse-protection rate limit."
            )

        with st.form("create_customer_api_key_form", clear_on_submit=True):
            name = st.text_input(
                "New API key name",
                placeholder="Portfolio automation",
                max_chars=80,
                help="Use a name that identifies the system or script that will use this key.",
            )
            create_clicked = st.form_submit_button(
                "Create Pro API key",
                type="primary",
                use_container_width=True,
                disabled=active_count >= 5,
            )

        if create_clicked:
            try:
                created = create_user_api_key(identity, name=name)
                st.session_state["new_customer_api_key_once"] = created
                st.rerun()
            except APIKeyStoreError as exc:
                st.error(str(exc))

        if rows:
            st.markdown("**Active keys**")
            for row in rows:
                key_id = str(row.get("id") or "")
                prefix = str(row.get("key_prefix") or "mfk_")
                label = str(row.get("name") or "API key")
                created_at = _short_timestamp(row.get("created_at"))
                last_used = _short_timestamp(row.get("last_used_at"))

                info_col, action_col = st.columns([4.2, 1])
                with info_col:
                    st.markdown(f"**{label}** · `{prefix}…`")
                    st.caption(
                        f"Created {created_at} · Last used {last_used}"
                    )
                with action_col:
                    if st.button(
                        "Revoke",
                        key=f"revoke_customer_api_key_{key_id}",
                        use_container_width=True,
                    ):
                        try:
                            revoke_user_api_key(identity, key_id)
                            st.session_state.pop("new_customer_api_key_once", None)
                            st.rerun()
                        except APIKeyStoreError as exc:
                            st.error(str(exc))
        else:
            st.caption("No active API keys yet.")

        st.markdown("---")
        st.markdown("**Using a key**")
        api_url = _api_public_url()
        if api_url:
            st.caption("Dedicated Pro API endpoint")
            st.code(f"{api_url}/api/v1", language="text")
            st.link_button(
                "Open API documentation",
                f"{api_url}/docs",
                use_container_width=True,
            )
        else:
            st.info(
                "The dedicated FastAPI hostname has not been published to this UI deployment yet. "
                "API keys remain safe to create/revoke, but programmatic requests require the separate API host."
            )

        st.code("X-API-Key: mfk_...", language="text")
        st.caption(
            "Send the key in the X-API-Key header. Each request re-checks the key and current Pro "
            "subscription authority. Revoked keys and accounts without active Pro access fail closed."
        )

        if api_url:
            with st.expander("Quickstart examples", expanded=False):
                st.markdown("**cURL**")
                st.code(
                    "curl -H \"X-API-Key: mfk_your_key_here\" "
                    f"\"{api_url}/api/v1/api/usage\"",
                    language="bash",
                )
                st.markdown("**Python**")
                st.code(
                    "import requests\n\n"
                    f'url = "{api_url}/api/v1/api/usage"\n'
                    'headers = {"X-API-Key": "mfk_your_key_here"}\n'
                    "response = requests.get(url, headers=headers, timeout=15)\n"
                    "response.raise_for_status()\n"
                    "print(response.json())",
                    language="python",
                )
