# Market Forecaster 4.0.0 — Forecast Intelligence Platform

Built against GitHub `master` at **v3.9.0**.

## Why 4.0 is a consolidation milestone

Market Forecaster now has:

```text
3.6  causal 1D/5D/10D/20D targets + common OOS protocol
3.7  model tournament
3.8  feature-family ablation
3.9  P(up) calibration + adaptive uncertainty
```

4.0 turns those research components into one coherent forecasting platform.

It does **not** add a trading engine.

## Platform boundary

```text
Market data
    ↓
Point-in-time feature store
    ↓
Forecast Authority
    ↓
Horizon-specific calibrated forecast
    ↓
Canonical Forecast Contract
    ↓
Separate downstream consumer / Trading Engine
```

The Forecast Contract intentionally has no:

```text
entry
exit
stop loss
take profit
position size
shares
orders
portfolio weights
trade instructions
```

A contract-safety assertion rejects those execution-field names if they accidentally appear in the canonical payload.

## Forecast Authority

New local registry:

```text
.local/forecast_authority.json
```

Each canonical horizon has an explicit configuration:

```json
{
  "1": {
    "model": "xgboost",
    "context_family": "none",
    "sector_ticker": null,
    "calibration_window": 120,
    "enabled": true
  },
  "5": { "...": "..." },
  "10": { "...": "..." },
  "20": { "...": "..." }
}
```

Default:

```text
1D   XGBoost + base features
5D   XGBoost + base features
10D  XGBoost + base features
20D  XGBoost + base features
```

This is deliberately conservative.

3.7/3.8 research may justify changing a horizon to a different model or feature family, but **nothing is automatically promoted**.

Saving the authority is atomic.

## Canonical Forecast Contract

Schema:

```text
4.0-forecast-contract-v1
```

Top-level contract:

```json
{
  "schema_version": "4.0-forecast-contract-v1",
  "contract_id": "...",
  "ticker": "AAPL",
  "as_of": "...",
  "generated_at": "...",
  "status": "READY",
  "scope": "FORECAST_ONLY",
  "current_price": 250.0,
  "forecasts": [],
  "authority": [],
  "data_quality": {},
  "errors": [],
  "provenance": {},
  "disclaimer": "..."
}
```

Each horizon forecast includes:

```text
horizon_days
target_date
model
context_family
sector_ticker
feature_schema_version

expected_log_return
expected_return_pct
projected_price

probability_up_pct
calibration_status
calibration_samples

price_range_80
price_range_90
return_range_80_pct
return_range_90_pct

diagnostics
  OOS records
  probability evaluation count
  Brier score
  Brier skill
  ECE
  empirical 80% coverage
  empirical 90% coverage
  interval width

context_provenance
```

## Truthful feature provenance

If the authority says:

```text
5D = XGBoost + volatility context
```

but VIX context cannot be retrieved with sufficient point-in-time coverage, 4.0 does **not** silently run:

```text
5D = XGBoost + base features
```

Instead the 5D horizon reports an error and the contract becomes:

```text
PARTIAL
```

That preserves the meaning of the configured Forecast Authority.

## Contract status

```text
READY
  every enabled authority horizon produced a forecast

PARTIAL
  at least one enabled horizon succeeded, at least one failed

UNAVAILABLE
  no enabled horizon produced a contract forecast
```

## Persistent Forecast Contract snapshots

When requested, contracts are persisted under:

```text
.local/forecast_contracts/
    AAPL/
        latest.json
        <timestamp>_<contract_id>.json
```

Writes are atomic.

`latest.json` is a convenience pointer; timestamped history remains available for later forecast-vs-realized audit work.

## Cross-ticker Forecast Authority validation

4.0 can run the exact same authority across a basket such as:

```text
AAPL
MSFT
SPY
QQQ
TSLA
TMC
```

It aggregates by horizon/model/context:

```text
tickers with forecast
number calibrated
mean OOS calibration samples
mean Brier score
mean Brier skill vs 50%
mean ECE
mean 80% coverage
mean 90% coverage
```

This is descriptive evidence.

The validation job never updates the Forecast Authority.

## UI

Backtest/research flow now contains:

```text
3.7 Model Tournament
3.8 Feature Intelligence & Ablation
3.9 Probability Calibration & Adaptive Uncertainty
4.0 Forecast Intelligence Platform
```

The 4.0 panel provides:

```text
Forecast Authority editor
Save Forecast Authority
Generate canonical Forecast Contract
Persist contract snapshot
Raw JSON inspection
Recent snapshot list
Cross-ticker authority validation
```

## API

Protected endpoints:

```text
GET  /api/v1/forecast-authority
POST /api/v1/forecast-authority

GET  /api/v1/forecast-contract/AAPL
POST /api/v1/forecast-contract/AAPL/snapshot

GET  /api/v1/forecast-contract-latest/AAPL

GET  /api/v1/research/cross-ticker-authority
```

### Fresh contract

```text
GET /api/v1/forecast-contract/AAPL?period=10y&n_splits=6&test_size=20
```

A fresh contract is computationally heavier because its uncertainty layer regenerates OOS evidence.

### Downstream consumption recommendation

A downstream Trading Engine should generally read:

```text
GET /api/v1/forecast-contract-latest/AAPL
```

after Market Forecaster has generated and persisted a research-approved snapshot.

This keeps downstream consumption fast and prevents the consumer from retraining models simply because it requested a forecast.

## CLI

Generate a fresh contract:

```powershell
python -m market_forecaster.scripts.forecast_contract `
  --ticker AAPL `
  --period 10y
```

Generate and persist:

```powershell
python -m market_forecaster.scripts.forecast_contract `
  --ticker AAPL `
  --period 10y `
  --persist
```

Cross-ticker validation:

```powershell
python -m market_forecaster.scripts.cross_ticker_validation `
  --tickers AAPL,MSFT,SPY,QQQ,TSLA,TMC `
  --period 5y `
  --folds 4
```

## Install

From repo root:

```powershell
python market_forecaster_v2_forecast_intelligence_patch_4.0.0\apply_forecast_intelligence_patch_4_0_0.py

python -m compileall -q market_forecaster

python -m pytest `
  market_forecaster\tests\test_forecast_authority.py `
  market_forecaster\tests\test_research_snapshots.py `
  market_forecaster\tests\test_forecast_contract.py `
  market_forecaster\tests\test_cross_ticker_validation.py `
  -q

streamlit run market_forecaster\app.py
```

## Recommended operating workflow after 4.0

Rather than immediately building 4.1, use the platform to accumulate evidence:

```text
1. Run 3.7 tournament on representative tickers.
2. Run 3.8 ablations.
3. Run 3.9 calibration.
4. Explicitly configure 4.0 Forecast Authority.
5. Run cross-ticker validation.
6. Generate/persist daily or research-triggered Forecast Contracts.
7. Audit realized outcomes against stored contracts.
```

The strongest next engineering milestone after enough snapshots exist is a **Forecast Outcome Audit** that resolves stored contracts against realized prices and measures live calibration/drift over time.

That should be evidence-driven rather than adding more model complexity immediately.
