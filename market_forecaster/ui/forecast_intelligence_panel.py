"""Forecast Intelligence Platform UI for Market Forecaster 4.0."""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from market_forecaster.config import SHARED_AUTHORITY_ENABLED
from market_forecaster.core.cross_ticker_validation import validate_authority_across_tickers
from market_forecaster.core.forecast_authority import (
    AUTHORITY_SCHEMA_VERSION,
    authority_rows,
    load_authority_config,
    save_authority_config,
)
from market_forecaster.core.forecast_contract import build_forecast_contract
from market_forecaster.core.market_context import ALL_CONTEXT_FAMILIES, FAMILY_DESCRIPTIONS
from market_forecaster.core.model_tournament import model_registry
from market_forecaster.core.research_snapshots import list_contract_snapshots
from market_forecaster.services.shared_authority_store import (
    shared_authority_write_configuration_status,
)


def _available_authority_models() -> list[str]:
    return [
        row["name"]
        for row in model_registry()
        if row["available"] and row["name"] not in {"zero_return", "historical_mean"}
    ]


def _window_label(value) -> str:
    return "All OOS history" if value is None else str(value)


def render_forecast_intelligence_panel(current_ticker: str) -> None:
    st.subheader("🧠 Forecast Intelligence Platform — 4.0")
    st.caption(
        "One explicit Forecast Authority, one canonical contract, persistent research "
        "snapshots, and cross-ticker evidence. No trading or execution semantics."
    )

    config = load_authority_config(require_available_models=False)
    if config.get("load_warning"):
        st.warning(
            "Persisted Forecast Authority was invalid and the safe default was loaded: "
            + config["load_warning"]
        )

    models = _available_authority_models()
    contexts = ["none", *ALL_CONTEXT_FAMILIES]
    windows = ["60", "120", "250", "All OOS history"]

    st.markdown("**Forecast Authority — explicit configuration by horizon**")
    edited = {
        "schema_version": AUTHORITY_SCHEMA_VERSION,
        "horizons": {},
        "notes": list(config.get("notes", [])),
    }

    for row in authority_rows(config):
        horizon = int(row["horizon"])
        with st.expander(f"{horizon}D authority", expanded=(horizon == 5)):
            c1, c2, c3, c4 = st.columns(4)

            current_model = row.get("model", "xgboost")
            model_index = models.index(current_model) if current_model in models else 0
            with c1:
                model = st.selectbox(
                    "Model",
                    models,
                    index=model_index,
                    key=f"authority_model_{horizon}",
                )

            current_context = row.get("context_family", "none")
            context_index = contexts.index(current_context) if current_context in contexts else 0
            with c2:
                context = st.selectbox(
                    "Context family",
                    contexts,
                    index=context_index,
                    format_func=lambda x: (
                        "Base features"
                        if x == "none"
                        else f"{x} — {FAMILY_DESCRIPTIONS[x]}"
                    ),
                    key=f"authority_context_{horizon}",
                )

            current_window = _window_label(row.get("calibration_window", 120))
            window_index = windows.index(current_window) if current_window in windows else 1
            with c3:
                window_label = st.selectbox(
                    "Calibration window",
                    windows,
                    index=window_index,
                    key=f"authority_window_{horizon}",
                )

            with c4:
                enabled = st.checkbox(
                    "Enabled",
                    value=bool(row.get("enabled", True)),
                    key=f"authority_enabled_{horizon}",
                )

            sector_ticker = row.get("sector_ticker") or ""
            if context == "sector":
                sector_ticker = st.text_input(
                    "Sector ETF",
                    value=sector_ticker,
                    placeholder="Example: XLK",
                    key=f"authority_sector_{horizon}",
                ).upper().strip()

            edited["horizons"][str(horizon)] = {
                "model": model,
                "context_family": context,
                "sector_ticker": sector_ticker or None,
                "calibration_window": (
                    None if window_label == "All OOS history" else int(window_label)
                ),
                "enabled": enabled,
            }

    authority_write_allowed = True
    authority_write_reason = ""
    if SHARED_AUTHORITY_ENABLED:
        authority_write_allowed, authority_write_reason = (
            shared_authority_write_configuration_status()
        )
        if not authority_write_allowed:
            st.caption(
                "Production Forecast Authority is shared and read-only in this app session. "
                "Publish changes from a trusted admin environment. "
                + authority_write_reason
            )

    if st.button(
        "Save Forecast Authority",
        key="save_forecast_authority",
        disabled=not authority_write_allowed,
    ):
        try:
            saved = save_authority_config(edited)
            st.success(
                "Forecast Authority saved. Research results still do not auto-promote "
                "models or feature families."
            )
            st.session_state["forecast_authority_saved"] = saved
        except Exception as exc:
            st.error(f"Could not save Forecast Authority: {exc}")

    st.markdown("---")
    st.markdown("**Canonical Forecast Contract**")

    c1, c2, c3 = st.columns(3)
    with c1:
        contract_period = st.selectbox(
            "Contract history",
            ["5y", "10y"],
            index=1,
            key="contract_period",
        )
    with c2:
        contract_folds = st.slider(
            "Contract OOS folds",
            4, 8, 6, 1,
            key="contract_folds",
        )
    with c3:
        contract_test = st.slider(
            "Contract test observations/fold",
            15, 40, 20, 5,
            key="contract_test_size",
        )

    persist = st.checkbox(
        "Persist contract snapshot",
        value=True,
        key="persist_forecast_contract",
        help="Stores an immutable research snapshot plus latest.json under .local/forecast_contracts.",
    )

    if st.button(
        f"Generate 4.0 Contract — {current_ticker.upper()}",
        type="primary",
        key="generate_forecast_contract",
    ):
        with st.spinner("Building horizon-specific calibrated Forecast Contract..."):
            try:
                active = load_authority_config(require_available_models=True)
                contract = build_forecast_contract(
                    current_ticker,
                    period=contract_period,
                    authority_config=active,
                    n_splits=contract_folds,
                    test_size=contract_test,
                    persist=persist,
                )
                st.session_state["forecast_contract_result"] = contract
            except Exception as exc:
                st.error(f"Forecast Contract failed: {exc}")

    contract = st.session_state.get("forecast_contract_result")
    if contract and contract.get("ticker") == current_ticker.upper():
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Contract Status", contract.get("status", "N/A"))
        with m2:
            st.metric("Contract ID", str(contract.get("contract_id", ""))[:12])
        with m3:
            st.metric("As Of", str(contract.get("as_of", ""))[:10])
        with m4:
            st.metric("Horizons", len(contract.get("forecasts", [])))

        forecasts = pd.DataFrame(contract.get("forecasts", []))
        if not forecasts.empty:
            display = forecasts.copy()
            display["80% Low"] = display["price_range_80"].map(
                lambda x: x[0] if isinstance(x, list) and len(x) == 2 else None
            )
            display["80% High"] = display["price_range_80"].map(
                lambda x: x[1] if isinstance(x, list) and len(x) == 2 else None
            )
            display["90% Low"] = display["price_range_90"].map(
                lambda x: x[0] if isinstance(x, list) and len(x) == 2 else None
            )
            display["90% High"] = display["price_range_90"].map(
                lambda x: x[1] if isinstance(x, list) and len(x) == 2 else None
            )
            display = display.rename(columns={
                "horizon_days": "Horizon",
                "target_date": "Target Date",
                "model": "Model",
                "context_family": "Context",
                "expected_return_pct": "Expected Return %",
                "projected_price": "Projected Price",
                "probability_up_pct": "P(up) %",
                "calibration_status": "Calibration",
                "calibration_samples": "OOS Samples",
            })
            preferred = [
                "Horizon", "Target Date", "Model", "Context",
                "Expected Return %", "Projected Price", "P(up) %",
                "Calibration", "OOS Samples",
                "80% Low", "80% High", "90% Low", "90% High",
            ]
            st.dataframe(
                display[[c for c in preferred if c in display.columns]],
                use_container_width=True,
                hide_index=True,
            )

        if contract.get("errors"):
            with st.expander(f"Contract horizon errors ({len(contract['errors'])})"):
                st.dataframe(
                    pd.DataFrame(contract["errors"]),
                    use_container_width=True,
                    hide_index=True,
                )

        with st.expander("Canonical JSON contract"):
            st.code(json.dumps(contract, indent=2, default=str), language="json")

    snapshots = list_contract_snapshots(current_ticker, limit=10)
    if snapshots:
        with st.expander("Recent persisted Forecast Contracts"):
            st.dataframe(pd.DataFrame(snapshots), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("**Cross-Ticker Forecast Authority Validation**")
    st.caption(
        "Runs the same explicit authority configuration across a basket and aggregates "
        "calibration/coverage evidence. It does not modify the authority."
    )

    ticker_text = st.text_input(
        "Validation basket",
        value="AAPL,MSFT,SPY,QQQ,TSLA,TMC",
        key="authority_validation_tickers",
    )
    v1, v2, v3 = st.columns(3)
    with v1:
        validation_period = st.selectbox(
            "Basket history",
            ["5y", "10y"],
            index=0,
            key="authority_validation_period",
        )
    with v2:
        validation_folds = st.slider(
            "Basket folds",
            4, 6, 4, 1,
            key="authority_validation_folds",
        )
    with v3:
        validation_test = st.slider(
            "Basket test observations/fold",
            15, 30, 20, 5,
            key="authority_validation_test",
        )

    if st.button("Run Cross-Ticker Validation", key="run_authority_validation"):
        symbols = [x.strip().upper() for x in ticker_text.split(",") if x.strip()]
        with st.spinner("Running the Forecast Authority across the validation basket..."):
            try:
                active = load_authority_config(require_available_models=True)
                validation = validate_authority_across_tickers(
                    symbols,
                    period=validation_period,
                    authority_config=active,
                    n_splits=validation_folds,
                    test_size=validation_test,
                )
                st.session_state["authority_cross_ticker_validation"] = validation
            except Exception as exc:
                st.error(f"Cross-ticker validation failed: {exc}")

    validation = st.session_state.get("authority_cross_ticker_validation")
    if validation:
        st.metric(
            "Tickers Completed",
            f"{validation.get('tickers_completed', 0)} / {len(validation.get('tickers_requested', []))}",
        )
        summary = pd.DataFrame(validation.get("summaries", []))
        if not summary.empty:
            display = summary.rename(columns={
                "horizon_days": "Horizon",
                "model": "Model",
                "context_family": "Context",
                "tickers_with_forecast": "Tickers",
                "calibrated_tickers": "Calibrated",
                "mean_calibration_samples": "Mean OOS Samples",
                "mean_brier_score": "Mean Brier",
                "mean_brier_skill_vs_50_pct": "Mean Brier Skill %",
                "mean_expected_calibration_error": "Mean ECE",
                "mean_coverage_80_pct": "Mean 80% Coverage",
                "mean_coverage_90_pct": "Mean 90% Coverage",
            })
            st.dataframe(display, use_container_width=True, hide_index=True)

        failures = [
            row for row in validation.get("ticker_results", [])
            if row.get("status") == "ERROR"
        ]
        if failures:
            with st.expander(f"Ticker validation errors ({len(failures)})"):
                st.dataframe(pd.DataFrame(failures), use_container_width=True, hide_index=True)

    with st.expander("4.0 platform boundary"):
        st.markdown(
            "- Forecast Authority is an explicit forecasting configuration, not an execution policy."
        )
        st.markdown(
            "- The canonical contract contains return/price forecasts, P(up), uncertainty ranges, "
            "calibration diagnostics, feature/model provenance, and data-quality metadata."
        )
        st.markdown(
            "- The contract intentionally contains no entry, exit, stop, order, position-size, "
            "portfolio-weight, or trade instruction."
        )
        st.markdown(
            "- A separate trading engine may consume the contract and independently apply its own strategy/risk logic."
        )
