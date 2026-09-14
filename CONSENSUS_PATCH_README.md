# Market Forecaster 2.5.0 — Production Consensus Routing

This patch integrates validated XGBoost horizons into the existing regime-aware classic ensemble without allowing unproven XGBoost outputs to influence the production path.

## What it adds

- **Production Consensus** forecast path in the Ensemble tab.
- Only XGBoost horizons with a global `PASS` can affect the consensus.
- XGBoost validation now also tags each validation fold with the **causal training-window market regime**.
- A stricter **Regime Gate** requires:
  - the global XGBoost horizon gate to pass,
  - at least 2 validation folds matching the current regime,
  - >=2% improvement vs zero-return/last-price baseline,
  - >=50% directional accuracy,
  - >=60% 10-90 quantile coverage.
- Globally PASS XGBoost horizons without regime confirmation are capped at roughly **10-15%** anchor weight.
- Regime-confirmed PASS horizons can earn roughly **20-35%** anchor weight.
- XGBoost never fully replaces the classic ensemble.
- Daily consensus adjustments are interpolated in **log-price space** between accepted XGBoost horizon anchors.
- Existing ensemble conformal intervals are shifted with the consensus path; XGBoost Bear/Bull values remain scenario anchors and are not mislabeled as confidence intervals.
- New authenticated API endpoint: `GET /api/v1/consensus/{ticker}`.

## Prerequisites

Apply these first:

1. Production Foundation 2.1.x
2. Validation Lab 2.2.x
3. Regime Engine 2.3.1+
4. Multi-Horizon XGBoost 2.4.0

`xgboost==3.1.3` should already be installed from 2.4.0.

## Install

Extract this folder into the `market_forecaster_v2` repo root. From the repo root:

```bash
python market_forecaster_v2_consensus_patch_2.5.0/apply_consensus_patch_2_5_0.py
python -m compileall -q market_forecaster
pytest market_forecaster/tests/test_production_consensus.py market_forecaster/tests/test_xgb_multihorizon.py -q
streamlit run market_forecaster/app.py
```

If you are already inside the inner `market_forecaster` folder:

```bash
python ../market_forecaster_v2_consensus_patch_2.5.0/apply_consensus_patch_2_5_0.py
python -m compileall -q .
pytest tests/test_production_consensus.py tests/test_xgb_multihorizon.py -q
streamlit run app.py
```

## How to use it

1. Run a normal forecast with **Ensemble** enabled.
2. Open the **Ensemble** tab.
3. Run **XGBoost Multi-Horizon Scenarios**.
4. Review the new **Regime Gate** columns.
5. Scroll to **Production Consensus**.

If no XGBoost horizon passes, the Production Consensus will explicitly remain `ENSEMBLE_ONLY` and will not modify the classic ensemble forecast.

## Interpretation

The green Production Consensus line is the deployable candidate path. The classic validated ensemble remains visible for comparison. Purple diamond markers show the XGBoost anchors that were actually allowed to influence production.

A globally PASS XGBoost horizon with insufficient matching regime history can still contribute, but only at a deliberately low weight. Regime confirmation earns more weight because it is based on matching out-of-sample evidence rather than a hard-coded market-state rule.
