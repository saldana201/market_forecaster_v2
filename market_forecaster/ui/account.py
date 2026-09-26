"""Account UI for Market Forecaster 4.1.1 managed authentication."""
from __future__ import annotations

import time

import streamlit as st

from market_forecaster.auth.factory import auth_configuration_status, get_auth_provider
from market_forecaster.auth.browser_session_store import BrowserSessionError
from market_forecaster.auth.persistent_session import (
    issue_persistent_browser_session,
    revoke_persistent_browser_session,
)
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
from market_forecaster.services.subscriptions import normalize_requested_plan
from market_forecaster.services.user_data import (
    client_for_state,
    ensure_account_foundation,
    load_user_preferences,
    persistence_configuration_status,
    save_user_preferences,
)
from market_forecaster.ui.billing import render_billing_panel, render_plan_selector
from market_forecaster.ui.browser_session import browser_user_agent


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
        try:
            issue_persistent_browser_session(
                st.session_state,
                result,
                user_agent=browser_user_agent(),
            )
        except BrowserSessionError:
            st.session_state["auth_notice"] = (
                "Signed in, but persistent browser-session storage is temporarily unavailable."
            )
        st.query_params["view"] = "account"
        st.success("Signed in.")
        st.rerun()
    except InvalidCredentials:
        st.error("Email or password was not accepted.")
    except AuthProviderError as exc:
        st.error(f"Sign-in unavailable: {exc}")


def _confirmation_help_panel() -> None:
    with st.expander("Didn't receive your confirmation email?"):
        st.caption(
            "Resend is only for an account that was already created but is still awaiting email confirmation."
        )
        email = st.text_input(
            "Account email",
            key="account_resend_email",
            placeholder="you@example.com",
        )

        cooldown_until = float(
            st.session_state.get("account_resend_cooldown_until", 0.0) or 0.0
        )
        remaining = max(0, int(round(cooldown_until - time.time())))

        if remaining > 0:
            st.caption(f"Please wait about {remaining} seconds before requesting another email.")

        if st.button(
            "Resend confirmation email",
            key="account_resend_confirmation",
            use_container_width=True,
            disabled=remaining > 0,
        ):
            if not email.strip():
                st.warning("Enter the email address used to create the account.")
                return

            try:
                get_auth_provider().resend_confirmation(email.strip())
                st.session_state["account_resend_cooldown_until"] = time.time() + 60
                st.success(
                    "If this address has an unconfirmed account, a new confirmation email was requested. "
                    "Check Inbox and Spam before requesting another one."
                )
            except RateLimited as exc:
                retry = int(exc.retry_after_seconds or 60)
                st.session_state["account_resend_cooldown_until"] = (
                    time.time() + max(1, retry)
                )
                if "email rate limit exceeded" in str(exc).lower():
                    st.error(
                        "The Supabase Auth email sender has reached its project sending limit. "
                        "Additional confirmation emails will not be reliable until custom SMTP is configured."
                    )
                else:
                    st.warning(
                        f"Confirmation email requests are temporarily limited. Try again in about {retry} seconds."
                    )
            except AuthProviderError:
                # Keep the response non-enumerating. Do not reveal whether the
                # supplied address exists or is already confirmed.
                st.info(
                    "The confirmation request could not be completed right now. "
                    "Try again later or use Sign in if the account is already confirmed."
                )


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
        requested_plan = normalize_requested_plan(st.session_state.get("requested_plan"))
        result = provider.register(
            email.strip(),
            password,
            display_name.strip() or None,
            requested_plan=requested_plan,
        )
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
        try:
            issue_persistent_browser_session(
                st.session_state,
                result,
                user_agent=browser_user_agent(),
            )
        except BrowserSessionError:
            st.session_state["auth_notice"] = (
                "Account created, but persistent browser-session storage is temporarily unavailable."
            )
        st.query_params["view"] = "account"
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
                try:
                    issue_persistent_browser_session(
                        st.session_state,
                        existing,
                        user_agent=browser_user_agent(),
                    )
                except BrowserSessionError:
                    st.session_state["auth_notice"] = (
                        "Signed in, but persistent browser-session storage is temporarily unavailable."
                    )
                st.session_state.pop("account_signup_cooldown_until", None)
                st.query_params["view"] = "account"
                st.success("That account already exists. Signed you in instead.")
                st.rerun()
                return
        except AuthProviderError:
            pass

        message = str(exc).lower()
        retry = int(exc.retry_after_seconds or 60)
        st.session_state["account_signup_cooldown_until"] = time.time() + max(1, retry)

        if "email rate limit exceeded" in message:
            st.error(
                "Confirmation email sending is temporarily unavailable because the Supabase "
                "Auth email service has reached its project sending limit."
            )
            st.info(
                "This is an email-provider limit, not a problem with your password or account form. "
                "For production signups, configure a custom SMTP provider in Supabase Authentication. "
                "Until then, additional signup emails may not be delivered even if you retry."
            )
        else:
            st.warning(
                f"A signup request was already sent recently. Wait about {retry} seconds before "
                "requesting another confirmation email. If you already confirmed this account, "
                "use the Sign in tab instead of Create account."
            )
    except AuthProviderError as exc:
        st.error(f"Account creation unavailable: {exc}")


def _preferences_panel(identity) -> None:
    ready, reason = persistence_configuration_status()
    if not ready:
        return

    try:
        client = client_for_state(st.session_state, identity)
        preferences = load_user_preferences(client, identity)
    except PersistenceError as exc:
        st.warning(f"Preferences could not be loaded: {exc}")
        return

    with st.container(border=True):
        st.markdown("### Preferences")
        st.caption("These settings follow your account across browsers and devices.")

        current_ticker = str(preferences.get("default_ticker") or "").upper().strip()
        default_ticker = st.text_input(
            "Default ticker",
            value=current_ticker,
            placeholder="SPY",
            max_chars=20,
            key="account_default_ticker",
            help="This ticker opens automatically the next time your account preferences are loaded.",
        ).upper().strip()

        timezone_options = [
            "America/Chicago",
            "America/New_York",
            "America/Denver",
            "America/Los_Angeles",
            "UTC",
        ]
        current_timezone = str(preferences.get("timezone") or "America/Chicago")
        timezone_index = (
            timezone_options.index(current_timezone)
            if current_timezone in timezone_options
            else 0
        )
        timezone_value = st.selectbox(
            "Timezone",
            timezone_options,
            index=timezone_index,
            key="account_timezone",
        )

        if st.button(
            "Save preferences",
            key="account_preferences_save",
            use_container_width=True,
        ):
            try:
                saved = save_user_preferences(
                    client,
                    identity,
                    default_ticker=default_ticker or None,
                    timezone=timezone_value,
                    settings=preferences.get("settings")
                    if isinstance(preferences.get("settings"), dict)
                    else {},
                )
                st.session_state["user_preferences"] = saved
                st.session_state["_preferences_loaded_for"] = identity.auth_subject
                if default_ticker:
                    st.session_state["ticker"] = default_ticker
                st.success("Preferences saved.")
            except PersistenceError as exc:
                st.error(f"Could not save preferences: {exc}")


def _security_panel() -> None:
    with st.container(border=True):
        st.markdown("### Security")
        st.caption(
            "Change the password for the currently signed-in account. "
            "Market Forecaster sends the new password directly to Supabase Auth and does not store it."
        )

        new_password = st.text_input(
            "New password",
            type="password",
            key="account_new_password",
            help="Use at least 8 characters.",
        )
        confirm_password = st.text_input(
            "Confirm new password",
            type="password",
            key="account_new_password_confirm",
        )

        if st.button(
            "Update password",
            key="account_update_password",
            use_container_width=True,
        ):
            if len(new_password) < 8:
                st.warning("Use a password with at least 8 characters.")
                return
            if new_password != confirm_password:
                st.warning("Passwords do not match.")
                return

            auth = st.session_state.get(AUTH_SESSION_KEY) or {}
            token = auth.get("access_token") if isinstance(auth, dict) else None
            if not token:
                st.warning("Your account session is unavailable. Sign in again.")
                return

            try:
                get_auth_provider().update_password(str(token), new_password)
                st.success("Password updated successfully.")
            except AuthProviderError as exc:
                st.error(f"Password update unavailable: {exc}")


def _signed_in_account() -> None:
    identity = resolve_identity(st.session_state)
    profile = auth_profile(st.session_state)

    st.markdown("## Your Market Forecaster Account")
    st.caption("Authentication is active. Watchlists and portfolios can now persist securely when account storage is enabled.")

    persistence_ready, persistence_reason = persistence_configuration_status()

    requested_plan = normalize_requested_plan(st.session_state.get("requested_plan"))
    active_access = identity.plan.title()
    if identity.subscription_status == "bootstrap":
        active_access = f"{active_access} (temporary)"

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Active access", active_access)
    with c2:
        st.metric("Selected tier", requested_plan.title() if requested_plan else "Not selected")
    with c3:
        st.metric("Status", "Signed in")
    with c4:
        st.metric("Account storage", "Enabled" if persistence_ready else "Disabled")

    st.caption(f"Signed in as {profile.get('email') or '—'}")
    if requested_plan and identity.subscription_status == "bootstrap":
        st.info(
            f"You selected **{requested_plan.title()}**. Current Standard access is temporary bootstrap "
            "access while paid billing is disabled; your selected tier has not been changed."
        )

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

    _preferences_panel(identity)
    _security_panel()
    render_billing_panel()

    if st.button("Sign out", key="account_logout", use_container_width=True):
        auth = st.session_state.get(AUTH_SESSION_KEY) or {}
        token = auth.get("access_token") if isinstance(auth, dict) else None
        try:
            if token:
                get_auth_provider().logout(str(token))
        except AuthProviderError:
            pass
        revoke_persistent_browser_session(st.session_state)
        clear_authenticated_session(st.session_state)
        try:
            del st.query_params["view"]
        except Exception:
            pass
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

    selected_plan = render_plan_selector()
    st.caption(
        f"Continue with **{selected_plan.title()}** by signing in to an existing account "
        "or creating a new one. You can change the tier above before continuing."
    )

    login_tab, register_tab = st.tabs(["Sign in", "Create account"])
    with login_tab:
        _login_form()
    with register_tab:
        _register_form()

    _confirmation_help_panel()
