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
    __version__, BRAND, DISCLAIMER, ForecastRequest,
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

# AutoTune
from market_forecaster.autotune.tuner import run_autotune

# ===================================================================
# Page config
# ===================================================================
st.set_page_config(page_title=f"{BRAND} — Market Forecaster", layout="wide")

# ===================================================================
# Sidebar → returns a validated ForecastRequest
# ===================================================================
req = render_sidebar()

# ===================================================================
# Header
# ===================================================================
st.title("📊 Market Forecaster")
st.write(
    "Forecast and validate future market-price scenarios for stocks & crypto. "
    "Built around leakage-controlled research, uncertainty, and repeatable out-of-sample evidence."
)

if is_analyst():
    model_availability_badges()

# ===================================================================
# Tabs — progressive based on mode
# ===================================================================
if get_mode() == "Simple":
    tabs = st.tabs(["🔮 Forecast", "📚 Help"])
    tab_forecast, tab_help = tabs
    tab_ensemble = tab_sentiment = tab_seasonal = tab_backtest = tab_patterns = None
elif get_mode() == "Trader":
    tabs = st.tabs(["🔮 Forecast", "📊 Ensemble", "📅 Seasonal", "🔁 Backtest", "📚 Help"])
    tab_forecast, tab_ensemble, tab_seasonal, tab_backtest, tab_help = tabs
    tab_sentiment = tab_patterns = None
else:  # Analyst
    tabs = st.tabs(["🔮 Forecast", "📊 Ensemble", "💭 Sentiment", "📅 Seasonal", "🔁 Backtest", "📈 Patterns", "📚 Help"])
    tab_forecast, tab_ensemble, tab_sentiment, tab_seasonal, tab_backtest, tab_patterns, tab_help = tabs


# ===================================================================
# AutoTune handler (runs before forecast if triggered)
# ===================================================================
if st.session_state.pop("run_autotune", False):
    with tab_forecast:
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
# Forecast tab
# ===================================================================
with tab_forecast:
    if st.button("🚀 Run Forecast", type="primary", use_container_width=True):
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
                label="Integrated Signal" if integrated else "Trading Signal",
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
3. Click **🚀 Run Forecast**
4. Read the plain-English insight at the top of the results

### Modes
- **Simple** — Ticker + preset + one-click forecast. Best for quick checks.
- **Trader** — Adds horizon/holdout controls, AutoTune, backtest, ensemble, and exports.
- **Analyst** — Full access to Prophet parameters, pattern diagnostics, and all model internals.

### AutoTune (Trader mode)
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

### Signals
The integrated signal combines technical indicators (20%), chart patterns (15%),
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
