"""Pro API key management UI."""
from __future__ import annotations

import streamlit as st

from market_forecaster.core.entitlements import can_use_api
from market_forecaster.core.session_identity import resolve_identity
from market_forecaster.services.api_keys import (
    APIKeyStoreError,
    api_key_store_configuration_status,
    create_user_api_key,
    list_user_api_keys,
    revoke_user_api_key,
)
from market_forecaster.ui.design_system import render_section_header


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
            if st.button(
                "I've saved this key",
                key="api_key_acknowledge_once",
                use_container_width=True,
            ):
                st.session_state.pop("new_customer_api_key_once", None)
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
        st.code("X-API-Key: mfk_...", language="text")
        st.caption(
            "Send the key in the X-API-Key header. Each request re-checks the key and current Pro "
            "subscription authority. Revoked keys and accounts without active Pro access fail closed."
        )
