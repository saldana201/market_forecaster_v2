# Market Forecaster 3.4.0 — Multi-Ticker Opportunity Ranking

Built against GitHub `master` at v3.3.0.

## Purpose

3.4 ranks the latest governed 3.3 decision snapshots across a watchlist.

It does **not**:
- silently run forecasts for every ticker,
- change model routing,
- change the deployed champion,
- bypass 3.3 calibration/actionability gates,
- place trades.

Each ticker must already have a governed 3.3 decision snapshot from a normal
Ensemble forecast.

## Ranking score

The ranking begins with the 3.3 Opportunity Score and applies penalties for:

- calibration evidence quality,
- live fallback / cached data,
- deployment drift,
- decision snapshot age,
- high positive same-direction return correlation.

Evidence multipliers:

```text
CALIBRATED   1.00
LOW_SAMPLE   0.65
PROVISIONAL  0.35
```

Data multipliers:

```text
LIVE_PRIMARY    1.00
LIVE_FALLBACK   0.80
CACHE_FALLBACK  0.30
```

Same-direction correlation starts penalizing the second/lower-ranked symbol
above +0.60 and reaches a maximum 25% ranking penalty at +1.00.

## Research risk-budget caps

Only 3.3 actionable + calibrated opportunities receive a nonzero research
risk-budget share.

Default single-symbol cap:

```text
25%
```

If a symbol is >=0.85 correlated with a higher-ranked same-direction symbol,
its cap falls to:

```text
15%
```

Unallocated percentage is deliberately left unallocated instead of forcing the
watchlist to 100%.

These values are research concentration controls, not automatic trade sizing.

## UI

Backtest gains:

```text
Market Data Providers
Multi-Ticker Opportunity Ranking
Drift Monitoring & Deployment Policy
...
```

Enter a comma-separated watchlist and click **Rank Watchlist**.

The panel shows:

- rank,
- ticker,
- horizon,
- 3.3 recommendation,
- evidence state,
- actionability,
- raw opportunity score,
- diversification-adjusted ranking score,
- expected return,
- probability up,
- reward/risk,
- data mode,
- drift,
- decision age,
- same-direction correlation,
- correlation penalty,
- research risk-budget cap.

Missing tickers are listed explicitly and require their own governed Ensemble
forecast first.

## Runtime state

```text
market_forecaster/.local/opportunity_ranking/watchlist.json
market_forecaster/.local/opportunity_ranking/latest.json
```

## API

Protected endpoints:

```text
GET /api/v1/opportunity-ranking?tickers=SPY,AAPL,TMC&include_correlation=true

GET /api/v1/opportunity-ranking/latest
```

## Install

Keep the patch folder intact. The installer uses only the unique
`mf34_payload_v340` directory.

From repo root:

```powershell
python market_forecaster_v2_opportunity_ranking_patch_3.4.0\apply_opportunity_ranking_patch_3_4_0.py
python -m compileall -q market_forecaster
python -m pytest market_forecaster\tests\test_opportunity_ranking.py -q
streamlit run market_forecaster\app.py
```

## Expected early behavior

Some watchlist symbols will show as missing until you run a normal governed
Ensemble forecast for each one. This is intentional; 3.4 does not fabricate or
mass-generate decision snapshots.

## Next milestone

Recommended 3.5: portfolio state + position-aware ranking. Let the user enter or
connect current positions/cost basis, then compare new opportunities against
existing exposure, concentration, correlated risk, and exit/invalidation levels.
