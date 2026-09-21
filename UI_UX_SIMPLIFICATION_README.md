# Market Forecaster 4.0.1 — UI/UX Simplification

Built against GitHub `master` at **v4.0.0**.

## Goal

4.0 made Market Forecaster a coherent forecasting platform. 4.0.1 makes that platform understandable without training.

The default experience is now organized around the question:

> What does the system think this market may do next?

Technical research is still available, but it no longer competes with the answer.

## New navigation

```text
Forecast
Research Lab
System Health
Advanced
Help
```

### Forecast

The canonical 4.0 Forecast Contract drives the main screen.

A normal user sees:

```text
Current Price
Primary Projected Price
Expected Move
Chance of Finishing Higher
Forecast Evidence

1D / 5D / 10D / 20D outlook table
Expected 80% range
Forecast chart
Plain-language summary
```

Technical details are progressively disclosed under:

```text
Why this forecast?
Advanced model details
What do these numbers mean?
```

The main forecast page does not require the user to understand:

```text
Brier score
ECE
OOS folds
feature ablation
model tournament
conformal calibration
```

Those concepts remain available for research users.

## Research Lab

Research now tells a guided story:

```text
1. Compare Models
2. Test Inputs
3. Validate Confidence
4. Approve Setup
```

These map to the existing 3.7–4.0 capabilities:

```text
3.7 Model Tournament
3.8 Feature Intelligence / Ablation
3.9 Probability Calibration / Uncertainty
4.0 Forecast Authority / Contract
```

No research capability is removed.

## System Health

Operational detail moves away from the prediction screen:

```text
Data Status
  provider / failover / cache
  options snapshot history

Operations
  operations events
  governance / audit
  legacy deployment policy

Forecast Quality
  detailed validation diagnostics
```

## Advanced

The older forecasting architecture remains available for comparison and compatibility:

```text
Prophet
AutoTune
Ensemble
Seasonal
Sentiment
Chart patterns
Opportunity ranking
Portfolio state
```

It is explicitly labeled legacy/advanced so users do not confuse it with the 4.0 Forecast Contract.

The old primary "Trading Signal" label becomes:

```text
Legacy Model Signal
```

This reinforces the boundary between Market Forecaster and the separate Trading Engine.

## Simplified sidebar

The sidebar now shows only the ticker by default.

All old mode, preset, Prophet, ensemble, AutoTune, and optional-module controls are hidden under:

```text
Advanced / legacy controls
```

The canonical Forecast screen is the same regardless of legacy mode.

## Forecast Evidence labels

Research diagnostics are translated into:

```text
Strong
Moderate
Developing
Limited
```

The technical calibration metrics remain visible under Advanced model details.

`Strong` is deliberately conservative: it requires calibrated status, at least 80 calibration observations, Brier score below 0.25, and reasonable historical 80% interval coverage.

## Forecast chart

The main chart shows:

```text
Current price
Projected 1D / 5D / 10D / 20D prices
80% expected range
```

It does not expose raw research diagnostics on the chart.

## Performance

The page first loads the latest persisted Forecast Contract when one exists. This makes routine viewing fast.

The user clicks:

```text
Refresh Forecast
```

only when they want Market Forecaster to regenerate the horizon models/calibration and persist a new snapshot.

Default refresh profile:

```text
5 years history
4 validation folds
20 observations/fold
```

Deep settings remain under Forecast settings:

```text
10 years
6 validation folds
```

## Install

From repo root:

```powershell
python market_forecaster_v2_ui_simplification_patch_4.0.1\apply_ui_simplification_patch_4_0_1.py

python -m compileall -q market_forecaster

python -m pytest market_forecaster\tests\test_forecast_dashboard.py -q

streamlit run market_forecaster\app.py
```

## Scope

This is a presentation-layer release.

It does not alter:

```text
3.6 targets
3.7 model tournament logic
3.8 feature ablation logic
3.9 probability calibration
4.0 Forecast Authority
4.0 Forecast Contract schema
```

The 4.0 Forecast Contract remains the canonical forecasting authority.
