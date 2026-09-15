# Market Forecaster 3.3.0 — Forecast Calibration + Decision Layer

Built against GitHub `master` at **v3.2.0**.

## Purpose

3.3 translates the governed production forecast into a conservative decision
layer. It does **not** alter the champion, ensemble weights, regime routing,
XGBoost, or options promotion.

## Probability calibration

For each effective champion and 1D/5D/10D/20D horizon:

```text
residual = realized_return - historical_predicted_return
P(up | current forecast) = P(residual > -current_predicted_return)
```

A Beta(1,1) smoothing prior is applied.

Evidence states:

```text
< 8 resolved outcomes            → PROVISIONAL (no numeric probability)
8–19 resolved outcomes           → LOW_SAMPLE (shrunk toward 50%)
>=20 + >=5 unique market runs    → CALIBRATED
```

The app will not display a fully calibrated probability simply because a model
generated a forecast.

## Decision metrics

Per horizon:

- raw governed forecast return
- bias-adjusted expected return
- calibrated probability up
- empirical realized MAE
- reference entry = current observed close
- governed forecast target
- calibrated decision target
- lower/upper interval
- invalidation level
- reward/risk
- 0–100 opportunity score
- recommendation

Recommendations:

```text
LONG_SETUP
SHORT_SETUP
WAIT
RESEARCH_BULLISH
RESEARCH_BEARISH
```

Actionable LONG requires:
- CALIBRATED evidence
- P(up) >= 58%
- expected return >= 1%
- reward/risk >= 1.5x
- opportunity score >= 55
- valid interval-side invalidation
- no cached data
- no severe deployment drift

SHORT uses symmetric downside rules.

## Safety caps

- PROVISIONAL score capped at 25
- LOW_SAMPLE score capped at 45
- cached data score capped at 20 and blocks actionable setups
- live degraded/fallback data caps score
- drift WATCH caps score
- FROZEN/DEGRADED drift blocks actionable setups

## UI

The **Calibrated Decision Layer** appears directly below the governed production
chart in the Ensemble tab.

## Runtime snapshot

Latest decision state is persisted to:

```text
market_forecaster/.local/decision_layer/<TICKER>.json
```

## API

Protected endpoint:

```text
GET /api/v1/decision/AAPL
```

The endpoint returns the latest persisted governed decision snapshot. If no
governed Ensemble forecast has been run yet, it returns 404.

## Install

Keep the extracted patch folder intact. The installer uses only the unique
script-relative `mf33_payload_v330` folder.

From repo root:

```powershell
python market_forecaster_v2_decision_layer_patch_3.3.0\apply_decision_layer_patch_3_3_0.py
python -m compileall -q market_forecaster
python -m pytest market_forecaster\tests\test_decision_layer.py -q
streamlit run market_forecaster\app.py
```

## Expected early behavior

Because the audit/outcome system is still accumulating real realized forecasts,
many horizons will initially show `PROVISIONAL` or `LOW_SAMPLE`. That is correct.

3.3 deliberately does not manufacture historical calibration evidence.

## Next milestone

Recommended 3.4: portfolio / multi-ticker opportunity ranking. Rank validated
decision-layer opportunities across a watchlist while controlling concentration,
correlation, and data/evidence quality.
