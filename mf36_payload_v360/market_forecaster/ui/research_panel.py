"""Forecast Research Foundation UI for Market Forecaster 3.6."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.feature_store import build_feature_store
from market_forecaster.core.experiment_runner import DEFAULT_MODELS, run_research_experiment

def render_research_panel(current_ticker: str) -> None:
    st.subheader("🧪 Forecast Research Lab — 3.6")
    st.caption("Leakage-controlled multi-horizon research. This panel cannot change production model routing, deployment, ranking, portfolio state, or trading logic.")
    c1,c2,c3=st.columns(3)
    with c1:
        period=st.selectbox("Research history",["2y","5y","10y"],index=1,key="research_period")
    with c2:
        folds=st.slider("Walk-forward folds",3,8,5,1,key="research_folds")
    with c3:
        test_size=st.slider("Observations / test fold",10,40,20,5,key="research_test_size")
    selected_models=st.multiselect(
        "Research models",list(DEFAULT_MODELS),default=list(DEFAULT_MODELS),key="research_models",
        help="3.7 will add LightGBM, CatBoost, TCN, LSTM and Transformer challengers."
    )
    if st.button("Run 1D / 5D / 10D / 20D Experiment",type="primary",key="run_research_foundation"):
        if not selected_models:
            st.error("Select at least one research model.")
        else:
            with st.spinner("Building causal feature store and running purged walk-forward experiments..."):
                try:
                    market=fetch_stock_data(current_ticker,period,"1d")
                    if market.empty:
                        st.error(f"No research market data available for {current_ticker}.")
                    else:
                        feature_frame,metadata=build_feature_store(market,current_ticker)
                        result=run_research_experiment(feature_frame,models=selected_models,n_splits=folds,test_size=test_size)
                        result["ticker"]=current_ticker.upper()
                        result["dataset_metadata"]=metadata.to_dict()
                        st.session_state["research_foundation_result"]=result
                except Exception as exc:
                    st.error(f"Research experiment failed: {exc}")
    result=st.session_state.get("research_foundation_result")
    if not result or result.get("ticker")!=current_ticker.upper():
        st.info("Run the research experiment to benchmark future-return prediction under one common leakage-safe protocol.")
        return
    meta=result.get("dataset_metadata",{})
    c1,c2,c3,c4=st.columns(4)
    with c1: st.metric("Feature Schema",result.get("feature_schema_version","N/A"))
    with c2: st.metric("Features",result.get("feature_count",0))
    with c3: st.metric("Rows",meta.get("row_count",0))
    with c4: st.metric("Provider",meta.get("provider") or "Unknown")
    summaries=pd.DataFrame(result.get("summaries",[]))
    if summaries.empty:
        st.warning("No valid folds were produced. Increase the history period or reduce test/fold size.")
        return
    display=summaries.rename(columns={
        "horizon":"Horizon","model":"Model","folds_run":"Folds","observations":"OOS Obs",
        "return_mae_bps":"Return MAE (bps)","return_rmse_bps":"Return RMSE (bps)",
        "directional_accuracy_pct":"Direction %","price_smape_pct":"Price sMAPE %",
        "improvement_vs_zero_mae_pct":"MAE Lift vs Zero %","fold_win_rate_vs_zero_pct":"Fold Win %",
        "improvement_ci_low_pct":"Lift CI Low %","improvement_ci_high_pct":"Lift CI High %",
        "research_status":"Research Status",
    })
    preferred=["Horizon","Model","Research Status","Folds","OOS Obs","Return MAE (bps)","Return RMSE (bps)","Direction %","Price sMAPE %","MAE Lift vs Zero %","Fold Win %","Lift CI Low %","Lift CI High %"]
    st.dataframe(display[[c for c in preferred if c in display.columns]].sort_values(["Horizon","Return MAE (bps)"]),use_container_width=True,hide_index=True)
    promising=summaries[summaries["research_status"]=="PROMISING"]
    if not promising.empty:
        st.success("Research candidates with positive paired-fold evidence: "+", ".join(f"{row.model} ({int(row.horizon)}D)" for row in promising.itertuples())+". These remain research-only.")
    else:
        st.info("No candidate currently clears the stricter 3.6 PROMISING research threshold. That is a valid result; production is unchanged.")
    with st.expander("3.6 methodology"):
        for note in result.get("notes",[]): st.markdown(f"- {note}")
        st.markdown("- Canonical target: `log(Close[t+h] / Close[t])` for h ∈ {1,5,10,20}.")
        st.markdown("- Embargo is automatically at least the horizon so a training label cannot end inside the validation window.")
        st.markdown("- Current 3.6 features are deliberately restricted to causal price/volume/volatility state. Future feature families will be added through controlled ablation studies.")
