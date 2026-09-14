# Market Forecaster v2 — Production Hardening Patch 2.1.0

This is an **overlay patch** for `saldana201/market_forecaster_v2` as reviewed on 2026-09-13.

## Apply

1. Back up or commit your repo.
2. Extract this ZIP **into the repository root**, allowing the included files to overwrite matching paths.
3. From the repository root run:

```powershell
python .\apply_production_patch.py
python -m compileall -q market_forecaster
pytest
```

4. For the API in development:

```powershell
$env:MARKET_FORECASTER_ENV="development"
uvicorn market_forecaster.api.main:app --host 127.0.0.1 --port 8000
```

5. For production, configure at minimum:

```text
MARKET_FORECASTER_ENV=production
MARKET_FORECASTER_API_KEY=<strong secret>
MARKET_FORECASTER_ALLOWED_ORIGINS=https://your-ui-domain.example
MARKET_FORECASTER_ALLOW_CREDENTIALS=false
MARKET_FORECASTER_RATE_LIMIT_REQUESTS=30
MARKET_FORECASTER_RATE_LIMIT_WINDOW_SECONDS=60
```

Build the API container from repo root:

```powershell
docker build -f market_forecaster/Dockerfile -t market-forecaster:2.1.0 .
```

## What this patch changes

- Replaces displayed in-sample Prophet metrics with rolling out-of-sample evaluation.
- Lags price-derived technical regressors and removes backward-fill leakage.
- Stops current chart-pattern snapshot scores from being copied backward through model history.
- Adds Ridge to ARIMA/RF ensemble and learns weights from a common held-out validation window.
- Replaces model-disagreement/±5% ensemble intervals with validation-residual split-conformal intervals.
- Uses business-day future dates for equities and 7-day dates for `*-USD` crypto pairs.
- Adds market-data validation, retry/backoff, provider/freshness metadata, and ticker validation.
- Adds API-key auth, explicit CORS, request IDs, safe 500 responses, structured access logs, and basic rate limiting.
- Adds `/api/v1/ready` separately from liveness `/api/v1/health`.
- Pins the production dependency set and standardizes on Python 3.12.
- Runs the container as a non-root user.
- Adds GitHub Actions compile/lint/test/container-build gates.

## Important design decision

Pattern detection remains available to the UI and integrated signal engine, but is **not** used as a Prophet historical regressor in this release. The current detector uses confirmed swing points; using a single current pattern score across the full historical training set creates look-ahead leakage. A later release should build a causal, date-by-date pattern timeline before patterns return to the forecasting feature set.

## Known next production steps

- Replace simulated sentiment with a real provider or disable it entirely in paid/production output.
- Move rate limiting to Redis/API gateway before horizontal scaling.
- Add provider redundancy beyond yfinance for paid production use.
- Add persistent forecast-run metadata and audit history.
- Build CPCV/purged validation and transaction-cost strategy validation for the trading strategy layer.
- Add XGBoost multi-horizon and volatility/regime routing after the validation baseline is stable.
