"""Plain-language Forecast Dashboard for Market Forecaster 4.1.0."""
from __future__ import annotations

from datetime import datetime, timezone
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from market_forecaster.core.forecast_authority import load_authority_config
from market_forecaster.core.forecast_contract import build_forecast_contract
from market_forecaster.core.research_snapshots import load_latest_contract
from market_forecaster.core.session_identity import resolve_identity
from market_forecaster.services.forecast_access import CachedForecastUnavailable, load_demo_forecast


def _number(value):
    try:
        value = float(value)
        return value if np.isfinite(value) else None
    except Exception:
        return None


def _money(value) -> str:
    value = _number(value)
    return "—" if value is None else f"${value:,.2f}"


def _percent(value, *, signed: bool = False) -> str:
    value = _number(value)
    if value is None:
        return "—"
    return f"{value:+.1f}%" if signed else f"{value:.1f}%"


def expected_range(forecast: dict, level: int = 80) -> str:
    values = forecast.get(f"price_range_{int(level)}")
    if not isinstance(values, list) or len(values) != 2:
        return "—"
    low, high = _number(values[0]), _number(values[1])
    if low is None or high is None:
        return "—"
    return f"${low:,.2f} – ${high:,.2f}"


def evidence_quality(forecast: dict | None) -> str:
    if not forecast:
        return "Limited"
    status = str(forecast.get("calibration_status") or "").upper()
    samples = int(forecast.get("calibration_samples", 0) or 0)
    diag = forecast.get("diagnostics") or {}
    brier = _number(diag.get("brier_score"))
    coverage80 = _number(diag.get("coverage_80_pct"))
    if status == "CALIBRATED" and samples >= 80:
        if brier is not None and brier < 0.25 and coverage80 is not None and 70 <= coverage80 <= 90:
            return "Strong"
        return "Moderate"
    if status in {"CALIBRATED", "LOW_SAMPLE"} or samples >= 30:
        return "Developing"
    return "Limited"


def primary_forecast(forecasts: list[dict]) -> dict | None:
    if not forecasts:
        return None
    by_horizon = {int(row.get("horizon_days", -1)): row for row in forecasts}
    for horizon in (10, 5, 20, 1):
        if horizon in by_horizon:
            return by_horizon[horizon]
    return sorted(forecasts, key=lambda row: int(row.get("horizon_days", 999)))[0]


def outlook_label(expected_return_pct) -> str:
    value = _number(expected_return_pct)
    if value is None:
        return "unclear"
    if value >= 3.0:
        return "positive"
    if value >= 0.75:
        return "slightly positive"
    if value > -0.75:
        return "mixed"
    if value > -3.0:
        return "slightly negative"
    return "negative"


def _range_width(values):
    if not isinstance(values, list) or len(values) != 2:
        return None
    low, high = _number(values[0]), _number(values[1])
    if low is None or high is None:
        return None
    return high - low


def plain_language_summary(contract: dict) -> str:
    forecasts = contract.get("forecasts", [])
    anchor = primary_forecast(forecasts)
    if not anchor:
        return "No forecast horizon is currently available."
    horizon = int(anchor.get("horizon_days", 0))
    outlook = outlook_label(anchor.get("expected_return_pct"))
    prob = _number(anchor.get("probability_up_pct"))
    quality = evidence_quality(anchor).lower()
    probability_text = (
        "Direction probability is still developing."
        if prob is None else f"The estimated chance of finishing higher is {prob:.0f}%."
    )
    anchor_width = _range_width(anchor.get("price_range_80"))
    longer = [row for row in forecasts if int(row.get("horizon_days", 0)) > horizon]
    wider = bool(anchor_width is not None and any(
        _range_width(row.get("price_range_80")) is not None
        and _range_width(row.get("price_range_80")) > anchor_width
        for row in longer
    ))
    return (
        f"The current {horizon}-day outlook is {outlook}. {probability_text} "
        f"Forecast evidence is {quality}."
        + (" The expected range widens at longer horizons." if wider else "")
    )


def _contract_age_text(contract: dict) -> str:
    generated = contract.get("generated_at")
    if not generated:
        return "Saved forecast"
    try:
        stamp = pd.Timestamp(generated)
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        now = pd.Timestamp(datetime.now(timezone.utc))
        hours = max(0.0, (now - stamp).total_seconds() / 3600.0)
        if hours < 1:
            return "Updated less than an hour ago"
        if hours < 24:
            return f"Updated {int(hours)}h ago"
        return f"Updated {int(hours // 24)}d ago"
    except Exception:
        return "Saved forecast"


def _forecast_table(contract: dict) -> pd.DataFrame:
    rows = []
    for row in sorted(contract.get("forecasts", []), key=lambda x: int(x.get("horizon_days", 999))):
        rows.append({
            "Horizon": f"{int(row.get('horizon_days', 0))} days",
            "Projected Price": _money(row.get("projected_price")),
            "Expected Move": _percent(row.get("expected_return_pct"), signed=True),
            "Chance of Finishing Higher": _percent(row.get("probability_up_pct")),
            "Expected Range": expected_range(row, 80),
            "Evidence": evidence_quality(row),
        })
    return pd.DataFrame(rows)


def _plot_forecast(contract: dict):
    forecasts = sorted(contract.get("forecasts", []), key=lambda x: int(x.get("horizon_days", 999)))
    current = _number(contract.get("current_price"))
    if not forecasts or current is None:
        return None
    x, expected, low, high = [0], [current], [current], [current]
    for row in forecasts:
        point = _number(row.get("projected_price"))
        if point is None:
            continue
        horizon = int(row.get("horizon_days", 0))
        band = row.get("price_range_80")
        x.append(horizon)
        expected.append(point)
        if isinstance(band, list) and len(band) == 2:
            lo, hi = _number(band[0]), _number(band[1])
            low.append(point if lo is None else lo)
            high.append(point if hi is None else hi)
        else:
            low.append(point)
            high.append(point)
    if len(x) < 2:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=high, mode="lines", line=dict(width=0), name="Expected range", hovertemplate="%{y:$,.2f}<extra>Upper range</extra>"))
    fig.add_trace(go.Scatter(x=x, y=low, mode="lines", fill="tonexty", line=dict(width=0), name="Expected range", hovertemplate="%{y:$,.2f}<extra>Lower range</extra>"))
    fig.add_trace(go.Scatter(x=x, y=expected, mode="lines+markers", name="Projected price", hovertemplate="%{x} days: %{y:$,.2f}<extra></extra>"))
    fig.update_layout(height=360, margin=dict(l=20, r=20, t=20, b=20), xaxis_title="Forecast horizon (days)", yaxis_title="Price", legend=dict(orientation="h"))
    return fig


def _advanced_details(contract: dict) -> pd.DataFrame:
    rows = []
    for row in contract.get("forecasts", []):
        diag = row.get("diagnostics") or {}
        context = row.get("context_family")
        rows.append({
            "Horizon": f"{int(row.get('horizon_days', 0))}D",
            "Forecast model": str(row.get("model", "")).replace("_", " ").title(),
            "Market information used": "Price & volume" if context in (None, "none") else f"Price & volume + {str(context).replace('_', ' ')}",
            "Historical forecast tests": int(row.get("calibration_samples", 0) or 0),
            "Probability accuracy (Brier)": _number(diag.get("brier_score")),
            "Calibration error (ECE)": _number(diag.get("expected_calibration_error")),
            "80% range observed coverage": _number(diag.get("coverage_80_pct")),
            "90% range observed coverage": _number(diag.get("coverage_90_pct")),
        })
    return pd.DataFrame(rows)


def _generate_contract(ticker: str, period: str, folds: int) -> dict:
    active = load_authority_config(require_available_models=True)
    return build_forecast_contract(ticker, period=period, authority_config=active, n_splits=folds, test_size=20, persist=True)


def render_forecast_dashboard(current_ticker: str) -> None:
    ticker = str(current_ticker or "").upper().strip()
    st.subheader(f"Forecast Outlook — {ticker}")
    st.caption("A plain-language view of the active forecasting setup. Technical research details are in Research Lab.")

    identity = resolve_identity(st.session_state)
    is_demo = identity.plan == "demo" and not identity.authenticated

    if is_demo:
        try:
            contract = load_demo_forecast(ticker).contract
        except CachedForecastUnavailable:
            contract = None
    else:
        saved = load_latest_contract(ticker)
        session_contract = st.session_state.get("simple_forecast_contract")
        contract = session_contract if session_contract and session_contract.get("ticker") == ticker else saved

    top_left, top_right = st.columns([4, 1])
    with top_left:
        st.caption(
            f"{_contract_age_text(contract)} · Data through {str(contract.get('as_of', ''))[:10]}"
            if contract else "No saved forecast is available yet."
        )
    with top_right:
        refresh_clicked = False if is_demo else st.button(
            "Refresh Forecast" if contract else "Generate Forecast",
            type="primary",
            use_container_width=True,
            key="simple_generate_forecast",
        )
        if is_demo:
            st.caption("Shared cached Demo forecast")

    period = "5y"
    folds = 4
    if not is_demo:
        with st.expander("Forecast settings", expanded=False):
            st.selectbox("History used", ["Standard — 5 years", "Deep — 10 years"], index=0, key="simple_contract_history", help="More history is slower but provides more calibration evidence.")
            st.selectbox("Validation depth", ["Standard", "Deep"], index=0, key="simple_contract_validation", help="Deep validation uses more historical test periods and takes longer.")
        period = "10y" if st.session_state.get("simple_contract_history", "").startswith("Deep") else "5y"
        folds = 6 if st.session_state.get("simple_contract_validation") == "Deep" else 4

    if refresh_clicked:
        with st.spinner("Updating 1-day, 5-day, 10-day and 20-day forecasts and checking uncertainty..."):
            try:
                contract = _generate_contract(ticker, period, folds)
                st.session_state["simple_forecast_contract"] = contract
            except Exception as exc:
                st.error(f"Forecast could not be generated: {exc}")
                return

    if not contract:
        if is_demo:
            st.warning(
                "This Demo symbol does not have a cached Forecast Contract yet. "
                "Run the scheduled Demo refresh job; anonymous traffic will not trigger training."
            )
        else:
            st.info("Generate a forecast to see projected prices, expected moves, direction probability, and uncertainty ranges.")
        return

    if contract.get("status") == "PARTIAL":
        st.warning("Some forecast horizons are temporarily unavailable. Available horizons are shown below.")
    elif contract.get("status") == "UNAVAILABLE":
        st.error("No forecast horizon is currently available.")
        return

    data_quality = contract.get("data_quality") or {}
    if data_quality.get("cache_used"):
        st.warning("Market data is coming from the last-known-good cache.")
    elif data_quality.get("provider_failover_used"):
        st.info("A validated backup market-data source is currently being used.")

    forecasts = contract.get("forecasts", [])
    anchor = primary_forecast(forecasts)
    h1, h2, h3, h4 = st.columns(4)
    with h1:
        st.metric("Current Price", _money(contract.get("current_price")))
    with h2:
        st.metric("Primary Projected Price", _money(anchor.get("projected_price")) if anchor else "—", delta=_percent(anchor.get("expected_return_pct"), signed=True) if anchor else None)
    with h3:
        st.metric("Chance of Finishing Higher", _percent(anchor.get("probability_up_pct")) if anchor else "—")
    with h4:
        st.metric("Forecast Evidence", evidence_quality(anchor))

    st.markdown("### Future Price Outlook")
    table = _forecast_table(contract)
    if not table.empty:
        st.dataframe(table, use_container_width=True, hide_index=True)

    fig = _plot_forecast(contract)
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Forecast Summary")
    st.info(plain_language_summary(contract))

    with st.expander("Why this forecast?"):
        st.write("Each horizon uses the active Forecast Authority model and approved market information. Probability and price ranges are checked against earlier out-of-sample forecasts.")
        why_rows = []
        for row in forecasts:
            context = row.get("context_family")
            why_rows.append({
                "Horizon": f"{int(row.get('horizon_days', 0))} days",
                "Forecast model": str(row.get("model", "")).replace("_", " ").title(),
                "Market information": "Price & volume" if context in (None, "none") else f"Price & volume + {str(context).replace('_', ' ')}",
                "Historical forecast tests": int(row.get("calibration_samples", 0) or 0),
                "Evidence": evidence_quality(row),
            })
        if why_rows:
            st.dataframe(pd.DataFrame(why_rows), use_container_width=True, hide_index=True)

    with st.expander("Advanced model details"):
        details = _advanced_details(contract)
        if not details.empty:
            st.dataframe(details, use_container_width=True, hide_index=True)
        st.caption("Probability accuracy (Brier): lower is better; 0.25 is the score of an uninformative constant 50% probability. Calibration error (ECE): lower is better. Observed coverage shows how often historical outcomes landed inside each range.")

    with st.expander("What do these numbers mean?"):
        st.markdown("""
- **Projected Price** — the model's central price estimate for that horizon.
- **Expected Move** — projected percentage change from today's price.
- **Chance of Finishing Higher** — calibrated estimate that the future price finishes above today's price.
- **Expected Range** — the model's 80% uncertainty range based on prior forecast errors.
- **Forecast Evidence** — plain-language indicator of how much calibration history exists and how well it has behaved.
        """)
