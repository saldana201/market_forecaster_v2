# Market Forecaster 3.1.0 — Production Operations & Monitoring

Built against the stabilized **3.0.1** baseline.

3.1 adds controlled automatic reconciliation, data/provider freshness checks,
execution-failure telemetry, audit coverage, drift-policy health, a Production
Operations dashboard, protected operations API endpoints, and a scheduler-ready
maintenance CLI.

Automatic maintenance runs after Production Consensus at most once every
30 minutes per ticker. It scores matured audit targets and refreshes governance,
deployment/drift state, freshness, and operations state.

Runtime files:

```text
market_forecaster/.local/operations/events.jsonl
market_forecaster/.local/operations/state/<TICKER>.json
```

Scheduler CLI:

```powershell
python -m market_forecaster.scripts.ops_maintenance --tickers SPY,AAPL,TMC --period 2y --force
```

Protected API:

```text
GET  /api/v1/operations/{ticker}
POST /api/v1/operations/{ticker}/run?period=2y&force=true
```

Install from repo root:

```powershell
python market_forecaster_v2_operations_patch_3.1.0\apply_operations_patch_3_1_0.py
python -m compileall -q market_forecaster
python -m pytest market_forecaster\tests\test_operations.py -q
streamlit run market_forecaster\app.py
```

The installer uses the uniquely named script-relative `mf31_payload_v310` folder.
It never reads a generic repo-root `payload/` directory.

Suggested Windows Task Scheduler cadence: once after market close on trading
days; daily for crypto.

Next recommended milestone: **3.2 provider abstraction + failover**, including a
last-known-good cache and provider quality comparison.
