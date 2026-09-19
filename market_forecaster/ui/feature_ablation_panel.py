"""Feature Intelligence / Ablation Lab UI for Market Forecaster 3.8."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.feature_store import build_feature_store
from market_forecaster.core.feature_ablation import (
    DEFAULT_ABLATION_MODELS,
    run_feature_ablation,
)
from market_forecaster.core.market_context import (
    ALL_CONTEXT_FAMILIES,
    DEFAULT_CONTEXT_FAMILIES,
    FAMILY_DESCRIPTIONS,
    build_market_context,
)
from market_forecaster.core.model_tournament import model_registry


def _tabular_models() -> list[str]:
    rows = model_registry()
    return [
        row["name"]
        for row in rows
        if row["available"]
        and not row["sequence"]
        and row["name"] not in {"zero_return", "historical_mean"}
    ]


def _preset_models(name: str) -> list[str]:
    available = set(_tabular_models())
    if name == "XGBoost focused":
        return [m for m in ("xgboost",) if m in available]
    if name == "Core ablation":
        return [
            m for m in ("ridge", "hist_gradient_boosting", "xgboost")
            if m in available
        ]
    return list(_tabular_models())


def render_feature_ablation_panel(current_ticker: str) -> None:
    st.subheader("🧬 Feature Intelligence & Ablation — 3.8")
    st.caption(
        "Hold the 3.7 model tournament fixed and test whether one new information "
        "family adds repeatable out-of-sample forecast lift."
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        period = st.selectbox(
            "Ablation history",
            ["2y", "5y", "10y"],
            index=1,
            key="ablation_period",
        )
    with c2:
        folds = st.slider(
            "Ablation folds",
            3, 8, 5, 1,
            key="ablation_folds",
        )
    with c3:
        test_size = st.slider(
            "Test observations/fold",
            10, 40, 20, 5,
            key="ablation_test_size",
        )
    with c4:
        preset = st.selectbox(
            "Model preset",
            ["XGBoost focused", "Core ablation", "Full tabular"],
            index=1,
            key="ablation_model_preset",
        )

    sector_ticker = st.text_input(
        "Optional sector ETF",
        value="",
        placeholder="Example: XLK, XLF, XLE",
        key="ablation_sector_ticker",
        help=(
            "Leave blank to skip sector features. 3.8 does not infer historical "
            "sector membership from today's company metadata."
        ),
    ).upper().strip()

    family_options = list(DEFAULT_CONTEXT_FAMILIES)
    if sector_ticker:
        family_options.append("sector")
    selected_families = st.multiselect(
        "Feature families to test",
        family_options,
        default=list(DEFAULT_CONTEXT_FAMILIES),
        format_func=lambda x: f"{x} — {FAMILY_DESCRIPTIONS[x]}",
        key="ablation_families",
    )

    models = _preset_models(preset)
    st.caption("Models used for feature attribution: " + ", ".join(models))

    if st.button(
        "Run Feature Ablation",
        type="primary",
        key="run_feature_ablation",
    ):
        if not selected_families:
            st.error("Select at least one feature family.")
        elif not models:
            st.error("No compatible tabular research models are available.")
        else:
            with st.spinner(
                "Fetching point-in-time context and running baseline-vs-family OOS comparisons..."
            ):
                try:
                    market = fetch_stock_data(current_ticker, period, "1d")
                    if market.empty:
                        st.error(f"No market data available for {current_ticker}.")
                    else:
                        base, metadata = build_feature_store(market, current_ticker)
                        enriched, registry = build_market_context(
                            base,
                            current_ticker,
                            period=period,
                            families=selected_families,
                            sector_ticker=sector_ticker or None,
                        )
                        result = run_feature_ablation(
                            base,
                            enriched,
                            registry,
                            families=selected_families,
                            models=models,
                            n_splits=folds,
                            test_size=test_size,
                        )
                        result["ticker"] = current_ticker.upper()
                        result["dataset_metadata"] = metadata.to_dict()
                        st.session_state["feature_ablation_result"] = result
                except Exception as exc:
                    st.error(f"Feature ablation failed: {exc}")

    result = st.session_state.get("feature_ablation_result")
    if not result or result.get("ticker") != current_ticker.upper():
        st.info(
            "Run an ablation to learn which external feature families improve "
            "the current price/volume forecasting baseline."
        )
        return

    registry = result.get("family_registry", {})
    registry_rows = []
    errors = []
    for family, info in registry.items():
        registry_rows.append({
            "Family": family,
            "Available": info.get("available"),
            "Features": info.get("feature_count"),
            "Coverage %": round(float(info.get("coverage_pct", 0.0)), 1),
            "Sources Used": ", ".join(info.get("sources_used", [])),
        })
        for err in info.get("source_errors", []):
            errors.append({"family": family, **err})

    if registry_rows:
        st.markdown("**Point-in-time context coverage**")
        st.dataframe(pd.DataFrame(registry_rows), use_container_width=True, hide_index=True)

    if errors:
        with st.expander(f"Context source warnings ({len(errors)})"):
            st.dataframe(pd.DataFrame(errors), use_container_width=True, hide_index=True)

    summaries = pd.DataFrame(result.get("family_summaries", []))
    if not summaries.empty:
        display = summaries.rename(columns={
            "family": "Family",
            "status": "Family Evidence",
            "feature_count": "Features",
            "coverage_pct": "Coverage %",
            "supported_tests": "Supported Tests",
            "mixed_tests": "Mixed Tests",
            "no_lift_tests": "No-Lift Tests",
            "mean_mae_lift_pct": "Mean MAE Lift %",
        })
        st.markdown("**Feature-family evidence summary**")
        st.dataframe(display, use_container_width=True, hide_index=True)

    comparisons = pd.DataFrame(result.get("comparisons", []))
    if not comparisons.empty:
        display = comparisons.rename(columns={
            "family": "Family",
            "horizon": "Horizon",
            "model": "Model",
            "folds": "Folds",
            "observations": "OOS Obs",
            "baseline_mae_bps": "Base MAE (bps)",
            "family_mae_bps": "+Family MAE (bps)",
            "mae_lift_pct": "MAE Lift %",
            "fold_win_rate_pct": "Fold Win %",
            "lift_ci_low_pct": "Lift CI Low %",
            "lift_ci_high_pct": "Lift CI High %",
            "baseline_direction_pct": "Base Direction %",
            "family_direction_pct": "+Family Direction %",
            "direction_delta_pct_points": "Direction Δ pp",
            "evidence_status": "Evidence",
        })
        preferred = [
            "Family", "Horizon", "Model", "Evidence", "Folds", "OOS Obs",
            "Base MAE (bps)", "+Family MAE (bps)", "MAE Lift %",
            "Fold Win %", "Lift CI Low %", "Lift CI High %",
            "Base Direction %", "+Family Direction %", "Direction Δ pp",
        ]
        st.markdown("**Detailed baseline vs +family comparisons**")
        st.dataframe(
            display[[c for c in preferred if c in display.columns]]
            .sort_values(["Family", "Horizon", "Model"]),
            use_container_width=True,
            hide_index=True,
        )

        supported = comparisons[comparisons["evidence_status"] == "SUPPORTED"]
        if not supported.empty:
            st.success(
                "Feature/horizon/model combinations with positive ablation evidence: "
                + ", ".join(
                    f"{row.family} {int(row.horizon)}D/{row.model}"
                    for row in supported.itertuples()
                )
            )
        else:
            st.info(
                "No feature family currently clears the strict SUPPORTED threshold. "
                "That is useful evidence; unsupported features should not be promoted."
            )

    with st.expander("3.8 methodology"):
        for note in result.get("notes", []):
            st.markdown(f"- {note}")
        st.markdown(
            "- Same-day context is allowed because the daily forecasting protocol "
            "already assumes forecasts are generated after Close[t]."
        )
        st.markdown(
            "- Context series are aligned backward only. A missing market day may "
            "use the most recent prior observation within the staleness limit, never a future one."
        )
        st.markdown(
            "- News and options-surface history are intentionally excluded until "
            "point-in-time historical datasets are available."
        )
