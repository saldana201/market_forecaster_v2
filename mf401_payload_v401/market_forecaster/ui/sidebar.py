"""Market Forecaster 4.0.1 sidebar — forecast first, advanced controls optional."""
from __future__ import annotations

import streamlit as st

from market_forecaster.config import (
    VALID_PERIODS,
    VALID_INTERVALS,
    VALID_GROWTH,
    VALID_SEASONALITY,
    CORE_PRESETS,
    PRO_PRESETS,
    ForecastRequest,
    __version__,
    BRAND,
)
from market_forecaster.ui.components import get_mode, is_trader, is_analyst, MODES


def render_sidebar() -> ForecastRequest:
    """Render a compact sidebar and return a compatible ForecastRequest."""
    with st.sidebar:
        st.markdown(f"**{BRAND}**")
        st.caption(f"Market Forecaster v{__version__}")

        st.markdown("### Forecast")
        ticker = st.text_input(
            "Ticker or crypto symbol",
            value=st.session_state.get("ticker", "SPY"),
            placeholder="AAPL, SPY, ETH-USD",
            help="The main Forecast page uses the active 4.0 Forecast Authority automatically.",
        ).strip().upper()
        st.session_state["ticker"] = ticker
        st.caption("Start on the Forecast tab. Research and technical controls are optional.")

        # Defaults kept for legacy/advanced tooling.
        period = st.session_state.get("p_period", "1y")
        interval = st.session_state.get("p_interval", "1d")
        horizon = st.session_state.get("p_horizon", 30)
        holdout = st.session_state.get("p_holdout_days", 15)
        growth = st.session_state.get("p_growth_mode", "linear")
        seas = st.session_state.get("p_seasonality_mode", "multiplicative")
        cps = float(st.session_state.get("p_cps", 0.10))
        sps = float(st.session_state.get("p_sps", 8.0))
        normalize_logistic = False
        use_options = bool(st.session_state.get("p_use_options", False))
        use_ensemble = bool(st.session_state.get("p_use_ensemble", False))
        use_sentiment = bool(st.session_state.get("p_use_sentiment", False))
        use_seasonal = bool(st.session_state.get("p_use_seasonal", False))

        with st.expander("Advanced / legacy controls", expanded=False):
            mode = st.radio(
                "Interface depth",
                MODES,
                index=MODES.index(st.session_state.get("app_mode", "Simple")),
                help=(
                    "Simple keeps legacy controls minimal. Trader exposes comparison tools. "
                    "Analyst exposes full legacy model internals. The canonical Forecast page is the same in every mode."
                ),
            )
            st.session_state["app_mode"] = mode

            all_presets = {"— Select preset —": {}}
            all_presets.update(CORE_PRESETS)
            if is_trader():
                all_presets.update(PRO_PRESETS)
            preset_name = st.selectbox("Legacy forecast preset", list(all_presets.keys()))
            if st.button("Apply legacy preset", use_container_width=True) and preset_name != "— Select preset —":
                for key, value in all_presets[preset_name].items():
                    st.session_state[f"p_{key}"] = value
                st.rerun()

            if is_trader():
                st.markdown("**Legacy forecast settings**")
                period = st.selectbox(
                    "History",
                    list(VALID_PERIODS),
                    index=list(VALID_PERIODS).index(period) if period in VALID_PERIODS else 3,
                )
                interval = st.selectbox(
                    "Interval",
                    list(VALID_INTERVALS),
                    index=list(VALID_INTERVALS).index(interval) if interval in VALID_INTERVALS else 0,
                )
                horizon = st.slider("Horizon (days)", 7, 180, int(horizon))
                holdout = st.slider("Holdout (days)", 5, 60, min(int(holdout), int(horizon)))

                st.markdown("**Optional legacy modules**")
                use_options = st.checkbox("Options Flow Analysis", value=use_options)
                use_ensemble = st.checkbox("Ensemble comparison", value=use_ensemble)
                use_sentiment = st.checkbox(
                    "Sentiment Analysis",
                    value=use_sentiment,
                    help="Currently uses simulated sentiment data.",
                )
                use_seasonal = st.checkbox("Seasonal Patterns", value=use_seasonal)

                st.markdown("**Legacy AutoTune**")
                budget = st.select_slider(
                    "Budget",
                    options=["Quick (12)", "Balanced (24)", "Deep (48)"],
                    value=st.session_state.get("autotune_budget", "Balanced (24)"),
                )
                st.session_state["autotune_budget"] = budget
                if st.button("Run Legacy AutoTune", use_container_width=True):
                    st.session_state["run_autotune"] = True

                from market_forecaster.autotune.config_store import ConfigStore
                best = ConfigStore().get(ticker)
                if best:
                    st.caption(
                        f"Best known legacy config updated {best.get('last_updated', 'N/A')[:10]}"
                    )
                    if st.button("Load Best Legacy Config", use_container_width=True):
                        for key, value in best.get("params", {}).items():
                            st.session_state[f"p_{key}"] = value
                        st.rerun()

            if is_analyst():
                st.markdown("**Prophet internals**")
                growth = st.selectbox(
                    "Growth",
                    list(VALID_GROWTH),
                    index=list(VALID_GROWTH).index(growth) if growth in VALID_GROWTH else 0,
                )
                seas = st.selectbox(
                    "Seasonality",
                    list(VALID_SEASONALITY),
                    index=list(VALID_SEASONALITY).index(seas) if seas in VALID_SEASONALITY else 0,
                )
                cps = st.slider("Changepoint Prior Scale", 0.01, 0.50, cps, 0.01)
                sps = st.slider("Seasonality Prior Scale", 0.1, 20.0, sps, 0.1)
                if growth == "logistic":
                    normalize_logistic = st.checkbox("Normalize for logistic stability", value=True)

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
