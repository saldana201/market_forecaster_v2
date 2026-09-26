"""
Market Forecaster — Streamlit Application
OneEight AI Systems

Run: streamlit run market_forecaster/app.py
     (from the directory that CONTAINS market_forecaster/)
"""

import sys
import os

# Ensure the parent directory is on the path so `market_forecaster` resolves
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import streamlit as st
from datetime import timedelta

from market_forecaster.config import (
    __version__, BRAND, DISCLAIMER, DATABASE_PERSISTENCE_ENABLED,
    DEMO_MODE_ENABLED, MULTI_USER_ENABLED, SUBSCRIPTIONS_ENABLED, ForecastRequest,
)
from market_forecaster.ui.sidebar import render_sidebar
from market_forecaster.ui.components import (
    get_mode, is_trader, is_analyst,
    show_disclaimer, show_simulated_warning,
    signal_card, component_breakdown, metric_row,
    model_availability_badges,
)
from market_forecaster.ui.plots import plot_forecast, plot_ensemble, plot_seasonal_bars
from market_forecaster.ui.insights import generate_forecast_insight, pattern_bias_label
from market_forecaster.ui.validation_panel import render_validation_panel
from market_forecaster.ui.regime_panel import render_regime_panel
from market_forecaster.ui.xgb_panel import render_xgb_panel
from market_forecaster.ui.consensus_panel import render_production_consensus_panel
from market_forecaster.ui.options_panel import render_options_flow_panel
from market_forecaster.ui.options_history_panel import render_options_history_panel
from market_forecaster.ui.governance_panel import render_governance_panel
from market_forecaster.ui.deployment_panel import render_deployment_policy_panel
from market_forecaster.ui.operations_panel import render_operations_panel
from market_forecaster.ui.provider_panel import render_provider_panel
from market_forecaster.ui.ranking_panel import render_opportunity_ranking_panel
from market_forecaster.ui.portfolio_panel import render_portfolio_panel
from market_forecaster.ui.research_panel import render_research_panel
from market_forecaster.ui.feature_ablation_panel import render_feature_ablation_panel
from market_forecaster.ui.uncertainty_panel import render_uncertainty_panel
from market_forecaster.ui.forecast_intelligence_panel import render_forecast_intelligence_panel
from market_forecaster.ui.forecast_dashboard import render_forecast_dashboard
from market_forecaster.ui.forecast_history import render_forecast_history
from market_forecaster.ui.research_workspace import render_research_workspace
from market_forecaster.ui.system_health_workspace import render_system_health_workspace
from market_forecaster.ui.advanced_tools_panel import render_advanced_tools_panel
from market_forecaster.ui.demo_landing import render_demo_landing
from market_forecaster.ui.demo_watchlist import render_demo_watchlist
from market_forecaster.ui.demo_portfolio import render_demo_portfolio
from market_forecaster.ui.demo_plans import render_demo_plans
from market_forecaster.ui.demo_theme import inject_market_forecaster_theme
from market_forecaster.ui.design_system import render_page_header
from market_forecaster.ui.account import render_account_screen
from market_forecaster.ui.billing import (
    capture_billing_return,
    render_billing_return_notice,
    render_upgrade_handoff,
)
from market_forecaster.ui.browser_session import (
    browser_user_agent,
    queue_browser_session_clear,
    render_browser_session_bridge,
)
from market_forecaster.ui.user_data_workspace import (
    render_persistent_watchlist,
    render_persistent_portfolio,
)

# Core
from market_forecaster.core.data import fetch_stock_data, get_close_series, infer_forecast_freq
from market_forecaster.core.indicators import add_technical_indicators
from market_forecaster.core.patterns import detect_chart_patterns, append_pattern_features
from market_forecaster.core.prophet_model import (
    prepare_for_prophet, fit_and_forecast, evaluate_oos,
)
from market_forecaster.core.ensemble import run_ensemble_forecast
from market_forecaster.core.sentiment import SentimentAnalyzer
from market_forecaster.core.seasonal import SeasonalAnalyzer
from market_forecaster.core.signals import compute_basic_signal, compute_integrated_signal
from market_forecaster.core.options_flow_v2 import fetch_options_flow_v2, persist_options_snapshot
from market_forecaster.core.operations import record_operation_event
from market_forecaster.core.session_identity import ensure_demo_session, resolve_identity
from market_forecaster.core.entitlements import can_view_research_lab, entitlements_for
from market_forecaster.auth.browser_session_store import BrowserSessionError
from market_forecaster.auth.factory import auth_configuration_status, get_auth_provider
from market_forecaster.auth.persistent_session import (
    ensure_persistent_browser_session,
    restore_persistent_browser_session,
    sync_persistent_browser_refresh_token,
)
from market_forecaster.auth.provider import AuthProviderError, InvalidToken
from market_forecaster.auth.session import AUTH_SESSION_KEY, sync_authenticated_identity
from market_forecaster.persistence.supabase_data import PersistenceError
from market_forecaster.services.subscriptions import (
    normalize_requested_plan,
    sync_subscription_identity,
)
from market_forecaster.services.user_data import hydrate_user_preferences

# AutoTune
from market_forecaster.autotune.tuner import run_autotune

# ===================================================================
# Page config
# ===================================================================
st.set_page_config(page_title=f"{BRAND} — Market Forecaster", layout="wide")
inject_market_forecaster_theme()
capture_billing_return()
browser_storage = render_browser_session_bridge(st.session_state)

# ===================================================================
# Sidebar → returns a validated ForecastRequest
# ===================================================================
ensure_demo_session(st.session_state)
if MULTI_USER_ENABLED:
    auth_ready, _auth_reason = auth_configuration_status()
    if auth_ready:
        # A hard browser refresh creates a new Streamlit Session State. Wait for
        # the tiny browser-storage component to report whether an opaque session
        # handle exists before deciding that this user belongs in Demo.
        if not browser_storage.ready:
            st.caption("Restoring secure account session…")
            st.stop()

        provider = get_auth_provider()
        current_auth = st.session_state.get(AUTH_SESSION_KEY)
        if (
            (not isinstance(current_auth, dict) or not current_auth.get("access_token"))
            and browser_storage.handle
        ):
            try:
                restored_identity = restore_persistent_browser_session(
                    st.session_state,
                    provider,
                    handle=browser_storage.handle,
                    user_agent=browser_user_agent(),
                )
                if restored_identity is None:
                    st.session_state["auth_notice"] = (
                        "Your saved browser session expired or was revoked. Please sign in again."
                    )
                    st.rerun()
            except InvalidToken:
                queue_browser_session_clear(st.session_state)
                st.session_state["auth_notice"] = (
                    "Your saved browser session expired. Please sign in again."
                )
                st.rerun()
            except (BrowserSessionError, AuthProviderError):
                st.warning(
                    "Your saved account session exists, but it cannot be restored right now "
                    "because the authentication service is temporarily unavailable."
                )
                if st.button(
                    "Retry account session",
                    key="retry_persistent_account_session",
                    type="primary",
                ):
                    st.rerun()
                st.stop()

        try:
            synced_identity = sync_authenticated_identity(st.session_state, provider)
            if synced_identity.authenticated:
                ensure_persistent_browser_session(
                    st.session_state,
                    synced_identity,
                    user_agent=browser_user_agent(),
                )
            sync_persistent_browser_refresh_token(st.session_state)
        except InvalidToken:
            queue_browser_session_clear(st.session_state)
            st.session_state["auth_notice"] = (
                "Your account session expired. Please sign in again."
            )
            st.rerun()
        except BrowserSessionError:
            st.session_state["auth_notice"] = (
                "Your account is signed in, but persistent browser-session storage "
                "is temporarily unavailable."
            )
        except AuthProviderError:
            st.session_state["auth_notice"] = (
                "Account verification is temporarily unavailable. Your current "
                "workspace will remain open while the provider recovers."
            )

if SUBSCRIPTIONS_ENABLED:
    current_identity = resolve_identity(st.session_state)
    if current_identity.authenticated:
        current_identity = sync_subscription_identity(st.session_state, current_identity)
        if current_identity.subscription_status == "unavailable":
            st.session_state["auth_notice"] = (
                "Subscription status is temporarily unavailable. Paid features are locked until it can be verified."
            )

if DATABASE_PERSISTENCE_ENABLED:
    current_identity = resolve_identity(st.session_state)
    if current_identity.authenticated:
        try:
            hydrate_user_preferences(st.session_state, current_identity)
        except PersistenceError:
            # Preferences are non-critical; keep the main forecast workspace
            # available if the persistence service is temporarily unavailable.
            pass

req = render_sidebar()
identity = resolve_identity(st.session_state)
is_demo = DEMO_MODE_ENABLED and not identity.authenticated
advanced_allowed = (
    not MULTI_USER_ENABLED
    or entitlements_for(identity).expensive_refreshes_per_day > 0
)

# ===================================================================
# Product shell
# ===================================================================
if is_demo:
    # Use Streamlit's segmented control instead of st.tabs for the public Demo
    # navigation. This avoids browser/theme-specific BaseWeb tab rendering issues
    # and only renders the selected Demo workspace on each rerun.
    demo_nav_options = (
        "◈ Discover",
        "★ Watchlist",
        "▣ Portfolio",
        "↗ Plans",
        "◎ Account",
        "? Help",
    )

    # Apply programmatic navigation before the segmented-control widget is
    # instantiated. Streamlit forbids changing a widget-backed session key
    # after that widget has been created during the same run.
    pending_demo_navigation = st.session_state.pop("demo_navigation_pending", None)
    if pending_demo_navigation in demo_nav_options:
        st.session_state["demo_navigation"] = pending_demo_navigation

    if st.session_state.get("demo_navigation") not in demo_nav_options:
        st.session_state["demo_navigation"] = demo_nav_options[0]

    demo_page = st.segmented_control(
        "Demo navigation",
        demo_nav_options,
        key="demo_navigation",
        label_visibility="collapsed",
    )
    demo_page = demo_page or demo_nav_options[0]

    if demo_page == "◈ Discover":
        selected = render_demo_landing(req.ticker)
        if selected != req.ticker:
            req.ticker = selected
        st.markdown("---")
        render_forecast_dashboard(req.ticker)

    elif demo_page == "★ Watchlist":
        render_demo_watchlist(req.ticker)

    elif demo_page == "▣ Portfolio":
        render_demo_portfolio()

    elif demo_page == "↗ Plans":
        render_demo_plans()

    elif demo_page == "◎ Account":
        notice = st.session_state.pop("auth_notice", None)
        if notice:
            st.warning(notice)
        render_account_screen()

    elif demo_page == "? Help":
        st.markdown("## Demo Guide")
        st.markdown(
            """
**Discover** shows the latest shared Forecast Contracts for the curated Demo universe.

**Watchlist** lets you collect up to six Demo markets during this session.

**Portfolio** lets you experiment with cash, quantity and cost basis for up to ten Demo positions.

Demo forecasts are never lower-quality forecasts. The upgrade boundary is broader ticker access,
persistent account data, advanced research tools and API access.

**Session note:** a browser disconnect, app recycle or expired Streamlit session can clear Demo state.
            """
        )
        show_disclaimer()

    st.markdown("---")
    st.caption(f"{BRAND} · Market Forecaster v{__version__} · Free Demo")
    st.stop()


# ===================================================================
# Internal / future authenticated workspace
# ===================================================================
notice = st.session_state.pop("auth_notice", None)
if notice:
    st.warning(notice)

render_billing_return_notice()
render_upgrade_handoff()

render_page_header(
    "Market Forecaster",
    "Clear multi-horizon market forecasts first. Research, system diagnostics, and legacy model controls stay available when you need them.",
    eyebrow="OneEight AI Systems",
    badge=f"{identity.plan.title()} workspace",
)

if is_analyst():
    model_availability_badges()

workspace_tab_labels = [
    "🔮 Forecast",
    "★ Watchlist",
    "▣ Portfolio",
    "↺ History",
    "◎ Account",
    "🧪 Research Lab",
    "🩺 System Health",
    "⚙️ Advanced",
    "📚 Help",
]
workspace_slug_by_label = {
    "🔮 Forecast": "forecast",
    "★ Watchlist": "watchlist",
    "▣ Portfolio": "portfolio",
    "↺ History": "history",
    "◎ Account": "account",
    "🧪 Research Lab": "research",
    "🩺 System Health": "health",
    "⚙️ Advanced": "advanced",
    "📚 Help": "help",
}
workspace_label_by_slug = {
    slug: label for label, slug in workspace_slug_by_label.items()
}

requested_view = st.query_params.get("view")
if isinstance(requested_view, list):
    requested_view = requested_view[0] if requested_view else None
default_workspace_tab = workspace_label_by_slug.get(
    str(requested_view or "").strip().lower(),
    "🔮 Forecast",
)


def _persist_workspace_tab() -> None:
    label = st.session_state.get("workspace_navigation")
    slug = workspace_slug_by_label.get(str(label or ""))
    if slug:
        st.query_params["view"] = slug


tab_forecast, tab_watchlist, tab_portfolio, tab_history, tab_account, tab_research, tab_health, tab_advanced, tab_help = st.tabs(
    workspace_tab_labels,
    default=default_workspace_tab,
    key="workspace_navigation",
    on_change=_persist_workspace_tab,
)

tab_ensemble = tab_advanced if is_trader() else None
tab_sentiment = tab_advanced if is_analyst() else None
tab_seasonal = tab_advanced if is_trader() else None
tab_patterns = tab_advanced if is_analyst() else None
tab_backtest = None

with tab_forecast:
    render_forecast_dashboard(req.ticker)

with tab_watchlist:
    render_persistent_watchlist(req.ticker)

with tab_portfolio:
    render_persistent_portfolio()

with tab_history:
    render_forecast_history()

with tab_account:
    render_account_screen()

with tab_research:
    if not MULTI_USER_ENABLED or can_view_research_lab(identity):
        render_research_workspace(req.ticker)
    else:
        st.markdown("## Research Lab")
        requested_plan = normalize_requested_plan(st.session_state.get("requested_plan"))
        if requested_plan == "pro":
            st.info(
                "Pro is selected for this account, but Pro entitlement is not active yet. "
                "Research Lab unlocks after the Pro subscription is confirmed by Stripe and "
                "subscription authority. Your standard Forecast Contract quality is unchanged."
            )
        else:
            st.info(
                "Research Lab is reserved for active Pro subscriptions. "
                "Standard accounts retain full Forecast Contract quality."
            )

with tab_health:
    render_system_health_workspace(req)

with tab_advanced:
    st.header("Advanced / Legacy Tools")
    if advanced_allowed:
        st.caption(
            "Older Prophet, ensemble, seasonal, sentiment, pattern, ranking, and portfolio tools remain here for comparison and compatibility. "
            "They do not replace the canonical 4.0 Forecast Contract shown on the Forecast page."
        )
        render_advanced_tools_panel(req.ticker)
    else:
        st.info(
            "Advanced model runs require Standard or Pro. "
            "Demo accounts use the shared cached Forecast Contracts."
        )


# ===================================================================
# AutoTune handler (runs before forecast if triggered)
# ===================================================================
if st.session_state.pop("run_autotune", False) and advanced_allowed:
    with tab_advanced:
        st.subheader(f"🔧 AutoTune for {req.ticker}")
        result = run_autotune(req, st.session_state.get("autotune_budget", "Balanced (24)"))

        if "error" in result and "leaderboard" not in result:
            st.error(result["error"])
        else:
            if "best_params" in result:
                st.success(f"Best config found! Stability score: {result['best_metrics']['stability_score']:.2f}")

                c1, c2, c3, c4 = st.columns(4)
                bp = result["best_params"]
                bm = result["best_metrics"]
                with c1:
                    st.metric("MAPE (mean)", f"{bm['mape_mean']:.2f}%")
                with c2:
                    st.metric("MAPE (std)", f"{bm['mape_std']:.2f}%")
                with c3:
                    st.metric("Dir. Accuracy", f"{bm['dir_accuracy']:.1f}%")
                with c4:
                    st.metric("Folds", bm["folds"])

                if st.button("✅ Apply Best Config"):
                    for k, v in bp.items():
                        st.session_state[f"p_{k}"] = v
                    st.rerun()

            if "leaderboard" in result:
                with st.expander("Full leaderboard"):
                    lb = result["leaderboard"]
                    display_cols = [c for c in ["stage", "growth", "seasonality_mode", "cps", "sps",
                                                 "mape_mean", "mape_std", "stability_score", "dir_accuracy", "folds"]
                                    if c in lb.columns]
                    st.dataframe(lb[display_cols].head(20), use_container_width=True)


# ===================================================================
# Advanced legacy forecast workflow
# ===================================================================
with tab_advanced:
    if advanced_allowed and st.button(
        "🚀 Run Forecast",
        type="primary",
        use_container_width=True,
    ):
        st.header(f"📈 {req.ticker}")

        # ---- Data ----
        with st.spinner("Fetching data..."):
            stock_df = fetch_stock_data(req.ticker, req.period, req.interval)
            if stock_df.empty:
                record_operation_event(req.ticker, "data_fetch", "ERROR", "Provider returned no market data")
                st.error(f"No data available for {req.ticker}")
                st.stop()
            if stock_df.attrs.get("is_cached"):
                record_operation_event(req.ticker, "data_provider", "WARN", "Last-known-good market-data cache is active", metadata={"provider": stock_df.attrs.get("provider"), "cache_age_days": stock_df.attrs.get("cache_age_days")})
                st.warning(f"Market-data fallback: using {stock_df.attrs.get('provider')} last-known-good cache. Forecasts are running in degraded data mode.")
            elif stock_df.attrs.get("provider_failover_used"):
                record_operation_event(req.ticker, "data_provider", "WARN", "Secondary market-data provider is active", metadata={"provider": stock_df.attrs.get("provider")})
                st.info(f"Primary market-data provider unavailable/rejected; using validated fallback provider: {stock_df.attrs.get('provider')}.")
            stock_df = add_technical_indicators(stock_df)
            record_operation_event(
                req.ticker, "data_fetch", "SUCCESS", "Market data fetch completed",
                metadata={"rows": len(stock_df), "provider": stock_df.attrs.get("provider")},
            )

        # ---- Patterns ----
        pattern_scores = detect_chart_patterns(stock_df)
        # Pattern snapshots remain UI/signal inputs only; do not backfill them through model history.
        st.session_state["pattern_scores"] = pattern_scores
        st.session_state["stock_df"] = stock_df

        # ---- Prophet ----
        with st.spinner("Training model..."):
            prophet_df = prepare_for_prophet(stock_df)

            model_kwargs = req.to_prophet_kwargs()

            # Logistic normalization
            y_min = y_range = None
            if req.growth_mode == "logistic" and req.normalize_logistic:
                y_min = prophet_df["y"].min()
                y_max = prophet_df["y"].max()
                y_range = max(y_max - y_min, 1.0)
                prophet_df["y"] = (prophet_df["y"] - y_min) / y_range
                prophet_df["cap"] = 1.2
                prophet_df["floor"] = 0

            model, forecast, contributions = fit_and_forecast(
                prophet_df, future_days=req.horizon,
                use_options=req.use_options, future_freq=infer_forecast_freq(req.ticker, req.interval), **model_kwargs,
            )

            # De-normalize
            if req.growth_mode == "logistic" and req.normalize_logistic and y_range:
                for col in ["yhat", "yhat_lower", "yhat_upper"]:
                    forecast[col] = forecast[col] * y_range + y_min
                prophet_df["y"] = prophet_df["y"] * y_range + y_min

        # Store for backtest
        st.session_state["prophet_model"] = model
        st.session_state["prophet_df"] = prophet_df

        # ---- Evaluation ----
        metrics = evaluate_oos(
            prophet_df,
            holdout_days=req.holdout_days,
            model_kwargs=model_kwargs,
            use_options=req.use_options,
            growth_mode=req.growth_mode,
            normalize_logistic=req.normalize_logistic,
            n_folds=3,
            future_freq=infer_forecast_freq(req.ticker, req.interval),
        )

        # ---- Enhanced models ----
        ensemble_result = None
        sentiment_data = None
        seasonal_signal = None
        seasonal_analysis = None
        options_flow_data = None
        st.session_state.pop("options_flow_v2", None)

        if req.use_options:
            with st.spinner("Analyzing options flow..."):
                try:
                    option_close = get_close_series(stock_df).dropna()
                    option_spot = float(option_close.iloc[-1]) if not option_close.empty else None
                    options_flow_data = fetch_options_flow_v2(req.ticker, spot=option_spot)
                    if options_flow_data.get("available"):
                        persist_options_snapshot(options_flow_data)
                    st.session_state["options_flow_v2"] = options_flow_data
                except Exception as e:
                    record_operation_event(req.ticker, "options_flow", "ERROR", str(e))
                    st.warning(f"Options flow error: {e}")

        if req.use_ensemble:
            with st.spinner("Running ensemble models..."):
                try:
                    ensemble_result = run_ensemble_forecast(
                        req.ticker, stock_df, req.horizon,
                        weights=st.session_state.get("regime_routing_weights"),
                    )
                    st.session_state["ensemble_result"] = ensemble_result
                except Exception as e:
                    record_operation_event(req.ticker, "ensemble", "ERROR", str(e))
                    st.warning(f"Ensemble error: {e}")

        if req.use_sentiment:
            with st.spinner("Analyzing sentiment..."):
                try:
                    sentiment_data = SentimentAnalyzer().analyze(req.ticker)
                    st.session_state["sentiment_data"] = sentiment_data
                except Exception as e:
                    record_operation_event(req.ticker, "sentiment", "ERROR", str(e))
                    st.warning(f"Sentiment error: {e}")

        if req.use_seasonal:
            with st.spinner("Analyzing seasonal patterns..."):
                try:
                    sa = SeasonalAnalyzer()
                    seasonal_analysis = sa.analyze_patterns(stock_df)
                    seasonal_signal = sa.get_current_signal()
                    st.session_state["seasonal_analysis"] = seasonal_analysis
                    st.session_state["seasonal_signal"] = seasonal_signal
                except Exception as e:
                    record_operation_event(req.ticker, "seasonal", "ERROR", str(e))
                    st.warning(f"Seasonal error: {e}")

        # ---- Signal ----
        basic_signal = compute_basic_signal(pattern_scores, stock_df, forecast)

        integrated = None
        if any([ensemble_result, sentiment_data, seasonal_signal, options_flow_data and options_flow_data.get("available")]):
            integrated = compute_integrated_signal(
                pattern_scores, stock_df, forecast,
                ensemble_result=ensemble_result,
                sentiment_data=sentiment_data,
                seasonal_signal=seasonal_signal,
                options_data=options_flow_data,
            )

        # ===========================================================
        # DISPLAY
        # ===========================================================

        # ---- Plain-English Insight (all modes) ----
        close = get_close_series(stock_df)
        last_price = float(close.iloc[-1]) if not close.empty else 0
        forecast_end = float(forecast["yhat"].iloc[-1])
        rsi_val = None
        try:
            rsi_col = stock_df.get("RSI_14")
            if rsi_col is not None:
                if isinstance(rsi_col, pd.DataFrame):
                    rsi_col = rsi_col.iloc[:, 0]
                rsi_val = float(rsi_col.dropna().iloc[-1])
        except Exception:
            pass

        ensemble_change = None
        if ensemble_result and ensemble_result["ensemble"][0] != 0:
            ensemble_change = (ensemble_result["ensemble"][-1] - ensemble_result["ensemble"][0]) / ensemble_result["ensemble"][0] * 100

        active_signal = integrated if integrated else basic_signal

        insight_text = generate_forecast_insight(
            ticker=req.ticker,
            horizon=req.horizon,
            last_price=last_price,
            forecast_end=forecast_end,
            mape=metrics.get("mape", np.nan),
            signal=active_signal.signal,
            pattern_bias=pattern_bias_label(pattern_scores),
            rsi=rsi_val,
            ensemble_change_pct=ensemble_change,
            sentiment_label=sentiment_data.get("sentiment_label") if sentiment_data else None,
            seasonal_rec=seasonal_signal.get("recommendation") if seasonal_signal else None,
        )

        st.info(insight_text)
        record_operation_event(
            req.ticker, "forecast_pipeline", "SUCCESS", "Forecast pipeline completed",
            metadata={"horizon": req.horizon, "ensemble_enabled": bool(req.use_ensemble)},
        )

        # ---- Signal card ----
        c1, c2 = st.columns([1, 2])
        with c1:
            signal_card(
                active_signal.signal, active_signal.score, active_signal.confidence,
                label="Legacy Integrated Signal" if integrated else "Legacy Model Signal",
            )
        with c2:
            if is_trader() and active_signal.components:
                component_breakdown(active_signal.components)

        # ---- Metrics ----
        if is_trader():
            st.subheader("Out-of-Sample Model Performance")
            metric_row({
                "MAE": metrics.get("mae", np.nan),
                "RMSE": metrics.get("rmse", np.nan),
                "MAPE %": metrics.get("mape", np.nan),
                "sMAPE %": metrics.get("smape", np.nan),
                "Dir. Accuracy %": metrics.get("directional_accuracy", np.nan),
            }, prefix="")

        # ---- Chart ----
        st.subheader("Forecast")
        merged = metrics.get("merged_df", pd.DataFrame())
        if not merged.empty:
            plot_forecast(
                merged, forecast,
                f"{req.ticker} — {req.horizon}-Day Forecast",
                tech_df=stock_df if is_trader() else None,
                show_technicals=is_trader(),
                history_df=prophet_df,
                pattern_scores=pattern_scores,
            )

        # ---- Regressor impact (Analyst) ----
        if is_analyst() and contributions:
            with st.expander("Regressor Impact"):
                impact = pd.DataFrame(
                    list(contributions.items()), columns=["Feature", "Avg Impact"],
                )
                impact["Abs Impact %"] = (impact["Avg Impact"].abs() * 100).round(2)
                impact = impact.sort_values("Abs Impact %", ascending=False)
                st.dataframe(impact, use_container_width=True)

        # ---- Pattern summary (Trader+) ----
        if is_trader():
            with st.expander("Chart Pattern Summary"):
                bias = pattern_bias_label(pattern_scores)
                st.markdown(f"**Overall bias:** `{bias}`")
                for name, score in sorted(pattern_scores.items(), key=lambda x: x[1], reverse=True):
                    if score >= 0.4:
                        st.markdown(f"- **{name}**: {score:.2f}")

        # ---- Export ----
        if is_trader():
            with st.expander("📥 Export"):
                export_df = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
                export_df.columns = ["Date", "Forecast", "Lower", "Upper"]
                csv = export_df.to_csv(index=False)
                st.download_button("Download CSV", csv, f"{req.ticker}_forecast.csv", "text/csv")

    show_disclaimer()


# ===================================================================
# Ensemble tab
# ===================================================================
if tab_ensemble:
    with tab_ensemble:
        st.header("📊 Ensemble Model Forecasting")
        result = st.session_state.get("ensemble_result")
        render_options_flow_panel(st.session_state.get("options_flow_v2"), st.session_state.get("stock_df"))
        render_regime_panel(st.session_state.get("stock_df"), result)
        render_xgb_panel(st.session_state.get("stock_df"), req.ticker, req.interval)
        render_production_consensus_panel(st.session_state.get("ensemble_result"), st.session_state.get("xgb_multihorizon_result"), req.ticker)
        if result:
            plot_ensemble(result, req.ticker)
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Models Used", ", ".join(result["models_used"]))
            with c2:
                change = (result["ensemble"][-1] - result["ensemble"][0]) / result["ensemble"][0] * 100 if result["ensemble"][0] != 0 else 0
                st.metric("Expected Change", f"{change:+.1f}%")
            with c3:
                avg_width = np.mean(result["upper"] - result["lower"])
                st.metric("Avg CI Width", f"${avg_width:.2f}")
        else:
            st.info("Run a forecast with **Ensemble** enabled to see results here.")


# ===================================================================
# Sentiment tab
# ===================================================================
if tab_sentiment:
    with tab_sentiment:
        st.header("💭 Market Sentiment")
        show_simulated_warning()

        data = st.session_state.get("sentiment_data")
        if data:
            import plotly.graph_objects as go

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Overall", f"{data['overall_sentiment']:.2f}", delta=data["sentiment_label"])
            with c2:
                st.metric("News", f"{data['news_sentiment']:.2f}")
            with c3:
                st.metric("Social", f"{data['social_sentiment']:.2f}")
            with c4:
                fg = data["fear_greed_index"]
                fg_label = ("Extreme Fear" if fg < 25 else "Fear" if fg < 45
                            else "Neutral" if fg < 55 else "Greed" if fg < 75
                            else "Extreme Greed")
                st.metric("Fear/Greed", f"{fg}/100", delta=fg_label)

            # Gauge
            fig = go.Figure(go.Indicator(
                mode="gauge+number", value=fg,
                domain={"x": [0, 1], "y": [0, 1]},
                title={"text": "Fear & Greed Index"},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": "darkblue"},
                    "steps": [
                        {"range": [0, 25], "color": "#ef4444"},
                        {"range": [25, 45], "color": "#f97316"},
                        {"range": [45, 55], "color": "#eab308"},
                        {"range": [55, 75], "color": "#84cc16"},
                        {"range": [75, 100], "color": "#22c55e"},
                    ],
                },
            ))
            fig.update_layout(height=280)
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("📰 Headlines"):
                for h in data.get("headlines", []):
                    st.markdown(f"- {h}")
        else:
            st.info("Run a forecast with **Sentiment** enabled to see results here.")


# ===================================================================
# Seasonal tab
# ===================================================================
if tab_seasonal:
    with tab_seasonal:
        st.header("📅 Seasonal Patterns")
        analysis = st.session_state.get("seasonal_analysis")
        signal = st.session_state.get("seasonal_signal")

        if analysis:
            if signal:
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("Seasonal Score", f"{signal['seasonal_score']:.3f}",
                              delta=signal["recommendation"])
                with c2:
                    months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                    best = analysis.get("monthly_best", 1)
                    st.metric("Best Month", months[best] if 1 <= best <= 12 else "N/A")
                with c3:
                    st.metric("Best Day", analysis.get("day_of_week_best", "N/A"))

                for s in signal.get("signals", []):
                    st.markdown(f"- {s}")

            plot_seasonal_bars(analysis)
        else:
            st.info("Run a forecast with **Seasonal** enabled to see results here.")


# ===================================================================
# Backtest tab
# ===================================================================
if tab_backtest:
    with tab_backtest:
        st.header("🔁 Prophet Backtest")
        render_governance_panel(req.ticker, st.session_state.get("stock_df"))
        st.markdown("---")
        render_operations_panel(req.ticker, st.session_state.get("stock_df"))
        st.markdown("---")
        render_provider_panel(req.ticker, st.session_state.get("stock_df"), req.interval)
        st.markdown("---")
        render_opportunity_ranking_panel(req.ticker)
        st.markdown("---")
        render_portfolio_panel()
        st.markdown("---")
        render_research_panel(req.ticker)
        st.markdown("---")
        render_feature_ablation_panel(req.ticker)
        st.markdown("---")
        render_uncertainty_panel(req.ticker)
        st.markdown("---")
        render_forecast_intelligence_panel(req.ticker)
        st.markdown("---")
        render_deployment_policy_panel(req.ticker)
        st.markdown("---")
        render_options_history_panel(req.ticker, st.session_state.get("stock_df"))
        st.markdown("---")
        render_validation_panel(req, st.session_state.get("stock_df"))
        st.markdown("---")
        model = st.session_state.get("prophet_model")
        hist = st.session_state.get("prophet_df")

        if model and hist is not None and not hist.empty:
            from prophet.diagnostics import cross_validation, performance_metrics

            hist_days = max(1, (hist["ds"].max() - hist["ds"].min()).days)
            st.write(f"History: ~{hist_days} days for **{req.ticker}**")

            max_h = max(7, min(hist_days // 3, 365))
            horizon_days = st.slider("Backtest horizon (days)", 7, max_h, min(90, max_h))

            if st.button("Run Backtest"):
                with st.spinner("Running cross-validation..."):
                    try:
                        df_cv = cross_validation(model, horizon=f"{horizon_days} days")
                        df_perf = performance_metrics(df_cv)
                        st.success("Backtest complete.")
                        st.dataframe(df_perf, use_container_width=True)

                        if "horizon" in df_perf.columns and "rmse" in df_perf.columns:
                            df_plot = df_perf.copy()
                            df_plot["horizon_days"] = df_plot["horizon"].dt.days
                            st.line_chart(df_plot.set_index("horizon_days")["rmse"])
                    except Exception as e:
                        st.error(f"Backtest failed: {e}")
        else:
            st.info("Run a forecast first to enable backtesting.")


# ===================================================================
# Patterns tab (Analyst only)
# ===================================================================
if tab_patterns:
    with tab_patterns:
        st.header("📈 Chart Pattern Dashboard")
        scores = st.session_state.get("pattern_scores")
        if scores:
            rows = [{"Pattern": k, "Score": v} for k, v in sorted(scores.items(), key=lambda x: x[1], reverse=True)]
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

            st.markdown("""
            **Scores:** 0.00 = not detected · 0.40+ = developing · 0.70+ = strong textbook pattern.
            Scores are current-snapshot signal inputs only; they are not historical model regressors until a causal pattern timeline is implemented.
            """)
        else:
            st.info("Run a forecast first to see pattern analysis.")


# ===================================================================
# Help tab
# ===================================================================
with tab_help:
    st.header("📚 Getting Started")
    st.markdown(f"""
### Quick Start (30 seconds)
1. Enter a ticker in the sidebar (e.g. `AAPL`, `SPY`, `ETH-USD`)
2. Pick a preset or leave defaults
3. Open **Forecast** and click **Generate Forecast** (or **Refresh Forecast**)
4. Read the plain-English outlook, probability, and expected range

### Workspaces
- **Forecast** — plain-language 1D / 5D / 10D / 20D outlook from the canonical Forecast Contract.
- **Research Lab** — guided model, feature, calibration, and Forecast Authority research.
- **System Health** — data freshness, providers, operations, governance, and validation diagnostics.
- **Advanced** — legacy Prophet/ensemble tools and expert controls kept for comparison and compatibility.

### Advanced / Legacy AutoTune
AutoTune searches for the best Prophet configuration by testing different combinations of
changepoint and seasonality parameters, then scoring them with a **stability penalty**:

> `score = mean_mape + 0.25 × std_mape`

This favors configs that are consistently good across multiple evaluation folds, not just
lucky on one window. Results are saved per-ticker so you can reload them instantly.

### Metrics
| Metric | What it means |
|--------|--------------|
| MAE | Average dollar error |
| RMSE | Penalizes large errors more |
| MAPE | Percentage error |
| sMAPE | Symmetric percentage (handles near-zero better) |
| Dir. Accuracy | % of days where predicted direction matches actual |

### Legacy Signals
The Advanced workspace retains the older integrated signal for comparison. It combines technical indicators (20%), chart patterns (15%),
options flow (15%), ensemble models (20%), sentiment (15%), and seasonal factors (15%).

### Limitations
- Sentiment analysis currently uses **simulated data** (labeled in the UI)
- Options analysis shows the current snapshot, not historical series
- Forecasts are statistical projections, not guarantees
    """)
    show_disclaimer()


# ===================================================================
# Footer
# ===================================================================
st.markdown("---")
st.caption(f"{BRAND} · Market Forecaster v{__version__}")
