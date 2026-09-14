# Market Forecaster 2.9.0 — Forecast Audit + Champion/Challenger Governance

Built against GitHub `master` after the v2.8 commit.

## What it adds

### Append-only forecast ledger

Every calculated Production Consensus is recorded under:

```text
market_forecaster/.local/forecast_audit/runs/<TICKER>.jsonl
```

It captures version, data timestamp/provider, regime, models, ensemble weights,
XGBoost anchors, options anchors, promotion state, and 1/5/10/20-session prices
for the validated ensemble, pre-options consensus, and final adaptive consensus.

Exact Streamlit reruns are fingerprint-deduplicated.

### Separate append-only outcome ledger

Original forecasts are never rewritten. Once target dates mature, realized closes
and errors are appended separately:

```text
market_forecaster/.local/forecast_audit/outcomes/<TICKER>.jsonl
```

### Champion/challenger governance

Backtest now includes **Forecast Audit & Champion/Challenger**.

It ranks:
- `validated_ensemble`
- `pre_options_consensus`
- `adaptive_production_consensus`

by realized absolute return error, price percentage error, directional accuracy,
resolved observations, and unique market snapshots.

Eligibility requires:
- at least 20 resolved predictions
- at least 5 unique market snapshots

The adaptive production consensus is the incumbent.

If a challenger beats incumbent realized-return MAE by at least 5% without
materially degrading direction accuracy, the recommendation becomes:

`REVIEW_CHALLENGER_PROMOTION`

v2.9 never changes routing automatically.

### Same-market-snapshot protection

All distinct runs are preserved for audit, but governance uses only the latest
production decision for each market-data timestamp. Same-day experiments cannot
create fake statistical weight.

## Workflow

1. Run a forecast with Ensemble enabled.
2. Production Consensus records the audit run automatically.
3. Later, open **Backtest → Forecast Audit & Champion/Challenger**.
4. Click **Score Matured Forecasts**.
5. As realized outcomes accumulate, the leaderboard becomes governance-eligible.

## API

Protected endpoints:

```text
GET  /api/v1/audit/{ticker}
POST /api/v1/audit/{ticker}/reconcile?period=2y
```

## Install

From repo root:

```bash
python market_forecaster_v2_governance_patch_2.9.0/apply_governance_patch_2_9_0.py
python -m compileall -q market_forecaster
pytest market_forecaster/tests/test_forecast_audit.py -q
streamlit run market_forecaster/app.py
```

From inside `market_forecaster/`:

```bash
python ../market_forecaster_v2_governance_patch_2.9.0/apply_governance_patch_2_9_0.py
python -m compileall -q .
pytest tests/test_forecast_audit.py -q
streamlit run app.py
```

## Source-control note

Audit ledgers are runtime evidence and belong under `.local`. Your `.gitignore`
already excludes `market_forecaster/.local`. If `.local` files were previously
committed, `.gitignore` does not untrack them automatically.

## Next milestone

Recommended 3.0: drift monitoring + explicit deployment policy. Use this audit
ledger to detect degradation by horizon/regime, freeze failing candidates, and
require explicit approval before a challenger becomes production champion.
