# Market Forecaster 3.0.0 — Drift Monitoring + Deployment Policy

Built against GitHub `master` after v2.9.

## What 3.0 changes

2.9 can identify a realized-performance leader. 3.0 turns that recommendation into an explicit governed deployment process.

### Drift monitoring

For each forecast candidate, 3.0 compares the most recent 10 resolved predictions against up to 20 older, non-overlapping resolved predictions. It monitors realized return MAE, directional accuracy, degradation percentage, and direction-accuracy drop.

Drift states:

- `COLLECTING` — insufficient recent/reference history
- `HEALTHY`
- `WATCH` — >=25% MAE degradation or >=10 percentage-point direction drop
- `FROZEN` — challenger >=50% MAE degradation, or severe direction deterioration
- `DEGRADED` — the same severe condition on the incumbent

The incumbent is never automatically replaced.

### Automatic challenger freeze

If an explicitly approved challenger later reaches `FROZEN`, its approval history remains intact, but the **effective** production champion falls back to `adaptive_production_consensus`.

### Explicit champion approval

A challenger does not become production champion merely because it leads the 2.9 leaderboard. Promotion requires all of:

1. Candidate is governance-eligible.
2. 2.9 recommendation is `REVIEW_CHALLENGER_PROMOTION`.
3. Candidate is the current eligible realized-performance leader.
4. Drift status is neither `COLLECTING` nor `FROZEN`.
5. Operator explicitly supplies candidate, approved-by identity, approval rationale, and confirmation.

Approvals are append-only under:

```text
market_forecaster/.local/forecast_audit/governance/<TICKER>.jsonl
```

Explicit rollback to the incumbent is always permitted.

### Governed forecast path

The Ensemble tab now resolves the approved/effective champion before drawing the production forecast.

Candidates:

- `validated_ensemble`
- `pre_options_consensus`
- `adaptive_production_consensus`

The audit record also captures approved champion, effective champion, deployment policy status, drift status, and approval event ID.

### Drift segmentation

Backtest → Drift Monitoring & Deployment Policy includes drift broken down by horizon and market regime.

## API

Protected endpoints:

```text
GET  /api/v1/deployment-policy/{ticker}

POST /api/v1/deployment-policy/{ticker}/approve
{
  "candidate": "validated_ensemble",
  "approved_by": "operator-name",
  "rationale": "Realized evidence supports promotion..."
}
```

A blocked promotion returns HTTP 409.

## Install

From repo root:

```bash
python market_forecaster_v2_deployment_policy_patch_3.0.0/apply_deployment_policy_patch_3_0_0.py
python -m compileall -q market_forecaster
pytest market_forecaster/tests/test_deployment_policy.py -q
streamlit run market_forecaster/app.py
```

From inside the inner package folder:

```bash
python ../market_forecaster_v2_deployment_policy_patch_3.0.0/apply_deployment_policy_patch_3_0_0.py
python -m compileall -q .
pytest tests/test_deployment_policy.py -q
streamlit run app.py
```

## Expected early behavior

Because 2.9 was just introduced, the deployment panel will initially show `COLLECTING`. The default/effective champion remains `adaptive_production_consensus` until enough real outcomes exist and an explicit approved change is recorded.

## Next milestone

Recommended 3.1: scheduled reconciliation + monitoring operations. Automatically score newly matured audit targets on a controlled cadence, surface drift alerts, and add a health dashboard for stale market data, failed provider requests, forecast execution failures, and audit/governance coverage.
