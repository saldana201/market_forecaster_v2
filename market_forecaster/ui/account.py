"""Account UI for Market Forecaster 4.1.1 managed authentication."""
from __future__ import annotations

import time

import streamlit as st

from market_forecaster.auth.factory import auth_configuration_status, get_auth_provider
from market_forecaster.auth.provider import AuthProviderError, InvalidCredentials, RateLimited
from market_forecaster.auth.session import (
    AUTH_SESSION_KEY,
    auth_profile,
    clear_authenticated_session,
    establish_authenticated_session,
)
from market_forecaster.config import MULTI_USER_ENABLED
from market_forecaster.core.session_identity import resolve_identity
from market_forecaster.persistence.supabase_data import PersistenceError
from market_forecaster.services.user_data import (
    ensure_account_foundation,
    persistence_configuration_status,
)


def _login_form() -> None:
    with st.form("account_login_form", clear_on_submit=False):
        email = st.text_input("Email", key="account_login_email")
        password = st.text_input("Password", type="password", key="account_login_password")
        submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)

    if not submitted:
        return
    if not email.strip() or not password:
        st.warning("Enter your email and password.")
        return

    try:
        provider = get_auth_provider()
        result = provider.login(email.strip(), password)
        if result.tokens is None:
            st.warning("Sign-in did not return an active session.")
            return
        establish_authenticated_session(
            st.session_state,
            result,
            provider_name=provider.name,
        )
        st.success("Signed in.")
        st.rerun()
    except InvalidCredentials:
        st.error("Email or password was not accepted.")
    except AuthProviderError as exc:
        st.error(f"Sign-in unavailable: {exc}")


def _register_form() -> None:
    with st.form("account_register_form", clear_on_submit=False):
        display_name = st.text_input("Display name", key="account_register_name")
        email = st.text_input("Email", key="account_register_email")
        password = st.text_input(
            "Password",
            type="password",
            key="account_register_password",
            help="Use at least 8 characters.",
        )
        confirm = st.text_input(
            "Confirm password",
            type="password",
            key="account_register_confirm",
        )
        submitted = st.form_submit_button("Create account", type="primary", use_container_width=True)

    if not submitted:
        return
    if not email.strip():
        st.warning("Enter an email address.")
        return
    if len(password) < 8:
        st.warning("Use a password with at least 8 characters.")
        return
    if password != confirm:
        st.warning("Passwords do not match.")
        return

    cooldown_until = float(st.session_state.get("account_signup_cooldown_until", 0.0) or 0.0)
    remaining = max(0, int(round(cooldown_until - time.time())))
    if remaining > 0:
        st.warning(
            f"A signup confirmation was requested recently. Please wait about {remaining} seconds, "
            "then try again only if you have not received the confirmation email."
        )
        return

    try:
        provider = get_auth_provider()
        result = provider.register(email.strip(), password, display_name.strip() or None)
        if result.requires_email_confirmation or result.tokens is None:
            st.session_state["account_signup_cooldown_until"] = time.time() + 60
            st.success(
                "Account request submitted. Check your email for the confirmation link, then return here to sign in. "
                "Do not press Create account again unless the email does not arrive after about a minute."
            )
            return
        establish_authenticated_session(
            st.session_state,
            result,
            provider_name=provider.name,
        )
        st.success("Account created and signed in.")
        st.rerun()
    except RateLimited as exc:
        # A repeated signup for an already-created account can hit Supabase's
        # confirmation cooldown. If the supplied password is valid, recover by
        # signing the user into the existing account instead of treating this
        # as another failed registration attempt.
        try:
            existing = provider.login(email.strip(), password)
            if existing.tokens is not None:
                establish_authenticated_session(
                    st.session_state,
                    existing,
                    provider_name=provider.name,
                )
                st.session_state.pop("account_signup_cooldown_until", None)
                st.success("That account already exists. Signed you in instead.")
                st.rerun()
                return
        except AuthProviderError:
            pass

        retry = int(exc.retry_after_seconds or 60)
        st.session_state["account_signup_cooldown_until"] = time.time() + max(1, retry)
        st.warning(
            f"A signup request was already sent recently. Wait about {retry} seconds before "
            "requesting another confirmation email. If you already confirmed this account, "
            "use the Sign in tab instead of Create account."
        )
    except AuthProviderError as exc:
        st.error(f"Account creation unavailable: {exc}")


def _signed_in_account() -> None:
    identity = resolve_identity(st.session_state)
    profile = auth_profile(st.session_state)

    st.markdown("## Your Market Forecaster Account")
    st.caption("Authentication is active. Watchlists and portfolios can now persist securely when account storage is enabled.")

    persistence_ready, persistence_reason = persistence_configuration_status()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Plan", identity.plan.title())
    with c2:
        st.metric("Status", "Signed in")
    with c3:
        st.metric("Email", profile.get("email") or "—")
    with c4:
        st.metric("Account storage", "Enabled" if persistence_ready else "Disabled")

    if persistence_ready:
        try:
            ensure_account_foundation(st.session_state, identity)
        except PersistenceError as exc:
            st.warning(f"Account storage could not initialize: {exc}")
    else:
        st.caption(f"Persistent storage is not active in this deployment: {persistence_reason}")

    with st.container(border=True):
        st.markdown("### Account identity")
        if profile.get("display_name"):
            st.write(f"**Name:** {profile['display_name']}")
        st.write(f"**Internal user ID:** {identity.user_id}")
        st.write(f"**Authentication provider:** {identity.auth_provider or 'managed'}")
        if profile.get("email_confirmed"):
            st.caption("Email confirmed")
        st.caption(
            "The internal user ID is derived from the verified provider identity. "
            "Browser requests cannot choose or override this ID."
        )

    if st.button("Sign out", key="account_logout", use_container_width=True):
        auth = st.session_state.get(AUTH_SESSION_KEY) or {}
        token = auth.get("access_token") if isinstance(auth, dict) else None
        try:
            if token:
                get_auth_provider().logout(str(token))
        except AuthProviderError:
            pass
        clear_authenticated_session(st.session_state)
        st.rerun()


def render_account_screen() -> None:
    identity = resolve_identity(st.session_state)
    if identity.authenticated:
        _signed_in_account()
        return

    st.markdown("## Sign in or create your Market Forecaster account")
    st.caption(
        "Already created or confirmed an account? Use Sign in—do not submit Create account again. "
        "Demo remains available without an account, while signed-in accounts can persist watchlists and portfolios."
    )

    if not MULTI_USER_ENABLED:
        st.info(
            "The 4.1.1 authentication foundation is installed but account access is disabled by "
            "the MULTI_USER_ENABLED feature flag."
        )
        return

    ready, reason = auth_configuration_status()
    if not ready:
        st.warning(f"Account provider is not configured: {reason}")
        return

    login_tab, register_tab = st.tabs(["Sign in", "Create account"])
    with login_tab:
        _login_form()
    with register_tab:
        _register_form()
