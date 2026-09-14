"""
Market Forecaster — Sidebar Configuration
Mode selector + progressive disclosure.
"""

import streamlit as st

from market_forecaster.config import (
    VALID_PERIODS, VALID_INTERVALS, VALID_GROWTH, VALID_SEASONALITY,
    CORE_PRESETS, PRO_PRESETS, ForecastRequest, get_plan, __version__, BRAND,
)
from market_forecaster.ui.components import get_mode, is_trader, is_analyst, MODES


def render_sidebar() -> ForecastRequest:
    """Render the sidebar and return a validated ForecastRequest."""

    with st.sidebar:
        st.markdown(f"**{BRAND}**")
        st.caption(f"Market Forecaster v{__version__}")

        # -------------------------------------------------------
        # Mode selector
        # -------------------------------------------------------
        st.subheader("🎛️ Mode")
        mode = st.radio(
            "Experience level",
            MODES,
            index=MODES.index(st.session_state.get("app_mode", "Simple")),
            horizontal=True,
            help="Simple = quick forecast · Trader = full controls · Analyst = everything",
        )
        st.session_state["app_mode"] = mode

        # -------------------------------------------------------
        # Ticker
        # -------------------------------------------------------
        st.subheader("📊 Ticker")
        ticker = st.text_input(
            "Symbol",
            value=st.session_state.get("ticker", "SPY"),
            placeholder="AAPL, SPY, ETH-USD",
        ).strip().upper()
        st.session_state["ticker"] = ticker

        # -------------------------------------------------------
        # Presets
        # -------------------------------------------------------
        all_presets = {"— Select preset —": {}}
        all_presets.update(CORE_PRESETS)
        if is_trader():
            all_presets.update(PRO_PRESETS)

        preset_name = st.selectbox("Preset", list(all_presets.keys()))

        if st.button("Apply preset") and preset_name != "— Select preset —":
            p = all_presets[preset_name]
            for k, v in p.items():
                st.session_state[f"p_{k}"] = v
            st.rerun()

        # -------------------------------------------------------
        # Forecast settings (Trader+)
        # -------------------------------------------------------
        period = st.session_state.get("p_period", "1y")
        interval = st.session_state.get("p_interval", "1d")
        horizon = st.session_state.get("p_horizon", 30)
        holdout = st.session_state.get("p_holdout_days", 15)

        if is_trader():
            st.subheader("🔮 Forecast")
            period = st.selectbox("History", list(VALID_PERIODS), index=list(VALID_PERIODS).index(period) if period in VALID_PERIODS else 3)
            interval = st.selectbox("Interval", list(VALID_INTERVALS), index=list(VALID_INTERVALS).index(interval) if interval in VALID_INTERVALS else 0)
            horizon = st.slider("Horizon (days)", 7, 180, int(horizon))
            holdout = st.slider("Holdout (days)", 5, 60, min(int(holdout), int(horizon)))

        # -------------------------------------------------------
        # Model settings (Analyst only)
        # -------------------------------------------------------
        growth = st.session_state.get("p_growth_mode", "linear")
        seas = st.session_state.get("p_seasonality_mode", "multiplicative")
        cps = float(st.session_state.get("p_cps", 0.10))
        sps = float(st.session_state.get("p_sps", 8.0))
        normalize_logistic = False

        if is_analyst():
            with st.expander("⚙️ Prophet Model", expanded=False):
                growth = st.selectbox("Growth", list(VALID_GROWTH), index=list(VALID_GROWTH).index(growth) if growth in VALID_GROWTH else 0)
                seas = st.selectbox("Seasonality", list(VALID_SEASONALITY), index=list(VALID_SEASONALITY).index(seas) if seas in VALID_SEASONALITY else 0)
                cps = st.slider("Changepoint Prior Scale", 0.01, 0.50, cps, 0.01)
                sps = st.slider("Seasonality Prior Scale", 0.1, 20.0, sps, 0.1)
                if growth == "logistic":
                    normalize_logistic = st.checkbox("Normalize for logistic stability", value=True)

        # -------------------------------------------------------
        # Advanced modules (Trader+)
        # -------------------------------------------------------
        use_options = bool(st.session_state.get("p_use_options", False))
        use_ensemble = bool(st.session_state.get("p_use_ensemble", False))
        use_sentiment = bool(st.session_state.get("p_use_sentiment", False))
        use_seasonal = bool(st.session_state.get("p_use_seasonal", False))

        if is_trader():
            with st.expander("🧠 Advanced Models", expanded=False):
                use_options = st.checkbox("Options Flow Analysis", value=use_options)
                use_ensemble = st.checkbox("Ensemble (ARIMA/RF/LSTM)", value=use_ensemble)
                use_sentiment = st.checkbox("Sentiment Analysis", value=use_sentiment,
                                           help="⚠️ Currently uses simulated data")
                use_seasonal = st.checkbox("Seasonal Patterns", value=use_seasonal)

        # -------------------------------------------------------
        # AutoTune (Trader+)
        # -------------------------------------------------------
        if is_trader():
            with st.expander("🔧 AutoTune", expanded=False):
                budget = st.select_slider(
                    "Budget",
                    options=["Quick (12)", "Balanced (24)", "Deep (48)"],
                    value=st.session_state.get("autotune_budget", "Balanced (24)"),
                )
                st.session_state["autotune_budget"] = budget

                if st.button("🔍 Run AutoTune", use_container_width=True):
                    st.session_state["run_autotune"] = True

                # Load best known
                from market_forecaster.autotune.config_store import ConfigStore
                store = ConfigStore()
                best = store.get(ticker)
                if best:
                    st.caption(f"Best known config for {ticker} (updated {best.get('last_updated', 'N/A')[:10]})")
                    if st.button("📂 Load Best Known", use_container_width=True):
                        for k, v in best.get("params", {}).items():
                            st.session_state[f"p_{k}"] = v
                        st.rerun()

        # -------------------------------------------------------
        # Build request
        # -------------------------------------------------------
        return ForecastRequest(
            ticker=ticker,
            period=period,
            interval=interval,
            horizon=horizon,
            holdout_days=holdout,
            growth_mode=growth,
            seasonality_mode=seas,
            cps=cps,
            sps=sps,
            normalize_logistic=normalize_logistic,
            use_options=use_options,
            use_ensemble=use_ensemble,
            use_sentiment=use_sentiment,
            use_seasonal=use_seasonal,
        )
