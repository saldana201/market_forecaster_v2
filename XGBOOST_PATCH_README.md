# Market Forecaster 2.4.0 — Multi-Horizon XGBoost + Quantile Scenarios

This patch adds a production-isolated XGBoost forecasting path without replacing Prophet, the classic ensemble, Model Zoo, or the Regime Engine.

## What it adds

- Direct cumulative-return forecasts at **1 / 5 / 10 / 20 sessions**.
- **10th / 50th / 90th percentile** conditional forecasts shown as Bear / Base / Bull scenarios.
- Causal technical/price/volume/calendar features.
- Purged expanding-window validation; the purge gap is at least the target horizon so training labels cannot overlap a validation block.
- Mandatory zero-return / last-price baseline.
- Per-horizon production gate based on baseline improvement, directional accuracy, fold coverage, and quantile coverage.
- Feature-importance panel (descriptive, not causal attribution).
- Authenticated `GET /api/v1/xgb/{ticker}` endpoint.

## Install

Extract this patch folder into the `market_forecaster_v2` repo root. From the repo root:

```bash
python market_forecaster_v2_xgboost_patch_2.4.0/apply_xgboost_patch_2_4_0.py
python -m pip install xgboost==3.1.3
python -m compileall -q market_forecaster
pytest market_forecaster/tests/test_xgb_multihorizon.py -q
streamlit run market_forecaster/app.py
```

If you are inside the inner `market_forecaster` folder, this is also valid:

```bash
python ../market_forecaster_v2_xgboost_patch_2.4.0/apply_xgboost_patch_2_4_0.py
python -m pip install xgboost==3.1.3
streamlit run app.py
```

## Where to find it

Run a normal forecast so price history is loaded. Open **Ensemble** and scroll below the Volatility + Regime Engine to **XGBoost Multi-Horizon Scenarios**. Click **Run Multi-Horizon XGBoost**.

## Production interpretation

A `PASS` is horizon-specific. A 5-session model may pass while 20-session remains HOLD. Do not treat a HOLD forecast as deployable simply because its Base scenario looks attractive.

The Bear/Base/Bull ranges are conditional model quantiles, not guaranteed 80% confidence intervals. The UI reports empirical validation coverage so you can see whether those quantiles are behaving reasonably out of sample.
