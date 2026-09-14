# Market Forecaster 3.2.0 — Market Data Provider Abstraction + Failover

Requires the working **3.1.0** baseline.

Default provider path:

```text
yfinance → Stooq → last-known-good cache
```

Stooq is an independent historical OHLCV fallback for supported US equity/ETF symbols. Unsupported Yahoo-style crypto/index/futures symbols skip Stooq instead of guessing a mapping. Crypto therefore falls back from yfinance to last-known-good cache unless another provider is added later.

Every live response passes a quality gate before forecasting: canonical OHLCV shape, completeness, positive closes, OHLC consistency, duplicate-date checks, minimum history, and an overall quality score. Failed responses are rejected.

Accepted live data is cached under:

```text
market_forecaster/.local/data_cache/
```

The default cache maximum age is 7 days. Cache fallback is always marked degraded and shown in the UI.

Environment controls:

```powershell
$env:MARKET_FORECASTER_DATA_PROVIDERS="yfinance,stooq"
$env:MARKET_FORECASTER_DATA_CACHE_ENABLED="true"
$env:MARKET_FORECASTER_DATA_CACHE_MAX_AGE_DAYS="7"
```

Backtest gains **Market Data Providers**, including selected provider, quality score, fallback state, provider attempt chain, and a manual independent provider comparison.

Protected API endpoints:

```text
GET /api/v1/data-providers/AAPL?period=1y&interval=1d
GET /api/v1/data-providers/AAPL/compare?period=1y&interval=1d
```

Install from the repo root:

```powershell
python market_forecaster_v2_provider_failover_patch_3.2.0\apply_provider_failover_patch_3_2_0.py
python -m compileall -q market_forecaster
python -m pytest market_forecaster\tests\test_data_providers.py market_forecaster\tests\test_operations.py -q
streamlit run market_forecaster\app.py
```

The installer uses only the uniquely named script-relative `mf32_payload_v320` directory. It never reads a generic repo-root `payload/` folder.

Recommended next milestone: **3.3 Forecast Calibration + Decision Layer** — calibrated probability-of-up, expected return, risk-adjusted opportunity score, and explicit entry/exit/invalidation levels derived from validated production forecasts.
