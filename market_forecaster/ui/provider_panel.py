from __future__ import annotations
import pandas as pd
import streamlit as st
from market_forecaster.core.data_providers import compare_market_data_providers, configured_provider_names, provider_runtime_summary

def render_provider_panel(ticker: str, stock_df=None, interval: str="1d") -> None:
    st.subheader("🔌 Market Data Providers")
    s=provider_runtime_summary(stock_df)
    c1,c2,c3,c4=st.columns(4)
    with c1: st.metric("Selected Provider",s.get("provider") or "None")
    with c2: st.metric("Quality",s.get("quality_status","UNKNOWN"))
    with c3:
        score=s.get("quality_score"); st.metric("Quality Score","N/A" if score is None else f"{float(score):.0f}/100")
    with c4: st.metric("Fallback","YES" if s.get("failover_used") else "NO")
    if s.get("cached"):
        age=s.get("cache_age_days"); st.warning("Last-known-good cache is active."+(f" Cache age: {float(age):.2f} days." if age is not None else ""))
    elif s.get("failover_used"): st.info("Primary provider failed or was rejected; a validated secondary provider is active.")
    attempts=pd.DataFrame(s.get("attempts",[]))
    if not attempts.empty:
        with st.expander("Provider attempt chain"): st.dataframe(attempts,use_container_width=True,hide_index=True)
    st.caption("Configured provider order: "+" → ".join(configured_provider_names())+" → last-known-good cache")
    if st.button("Compare Live Providers",key=f"provider_compare_{ticker}_{interval}"):
        with st.spinner("Fetching independent provider samples..."):
            try: st.session_state["provider_comparison"]=compare_market_data_providers(ticker,"1y",interval)
            except Exception as exc: st.error(f"Provider comparison failed: {exc}")
    comparison=st.session_state.get("provider_comparison")
    if comparison and comparison.get("ticker")==str(ticker).upper():
        rows=[]
        for name,info in comparison.get("providers",{}).items():
            q=info.get("quality") or {}; rows.append({"Provider":name,"Status":info.get("status"),"Score":q.get("score"),"Rows":q.get("rows"),"Last Market Timestamp":info.get("last_market_timestamp"),"Reason":info.get("reason")})
        if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        if comparison.get("pairwise"):
            st.markdown("**Cross-provider close comparison**"); st.dataframe(pd.DataFrame(comparison["pairwise"]),use_container_width=True,hide_index=True)
