# Market Forecaster 3.5.0 — Portfolio State + Position-Aware Ranking

Built against GitHub `master` at v3.4.0.

## Purpose

3.5 adds manual/local portfolio state and places a portfolio-risk overlay on top
of the existing 3.4 multi-ticker ranking.

It does **not**:
- connect a brokerage,
- place orders,
- auto-close positions,
- auto-resize holdings,
- increase the 3.4 research risk budget.

Existing exposure can only reduce new suggested research allocation.

## Portfolio state

Stored locally:

```text
market_forecaster/.local/portfolio/state.json
```

Fields:

```text
cash
ticker
quantity       (+ long / - short)
average cost basis
```

Use one aggregated row per ticker.

## Position valuation

3.5 retrieves recent market prices through the existing 3.2 provider/failover
layer. If live market pricing is unavailable, it can fall back to the latest
decision-layer reference entry for context.

The dashboard shows:

- position side,
- current quantity,
- cost basis,
- current price,
- portfolio weight,
- unrealized P/L,
- governed decision recommendation,
- decision invalidation,
- invalidation breach state.

## Position-aware ranking

The 3.4 ranking remains unchanged and reproducible.

3.5 creates a separate overlay that applies:

### Single-name concentration

Default limit:

```text
20% of gross capital base
```

A concentrated existing position reduces both rank score and new headroom.

### Correlated-cluster exposure

Default cluster limit:

```text
40%
```

Existing same-direction positions with return correlation >=0.70 consume
cluster headroom before a new research allocation can be suggested.

### Position conflicts

Examples:

```text
Current short + LONG_SETUP  -> POSITION_CONFLICT
Current long  + SHORT_SETUP -> POSITION_CONFLICT
```

New research budget becomes zero until the conflict is reviewed.

### Governed invalidation breach

If an existing long trades at/below its latest decision invalidation—or an
existing short trades at/above it—the position receives:

```text
EXIT_REVIEW
```

This is a review flag only. No order is placed.

### Portfolio actions

```text
NEW_ENTRY_CANDIDATE
NEW_SHORT_CANDIDATE
ADD_CANDIDATE
HOLD_MONITOR
POSITION_CONFLICT
EXIT_REVIEW
WATCH
```

## Capital weights

To support both long and short positions without hiding leverage, portfolio
concentration uses:

```text
capital base = cash + gross absolute exposure
```

The UI separately reports long and short gross exposure.

## UI

Backtest becomes:

```text
Market Data Providers
Multi-Ticker Opportunity Ranking
Portfolio State & Position-Aware Ranking   <- NEW
Drift Monitoring & Deployment Policy
...
```

Workflow:

1. Run governed Ensemble forecasts for watchlist names.
2. Run 3.4 Multi-Ticker Opportunity Ranking.
3. Enter cash and current positions.
4. Save Portfolio State.
5. Click **Build Position-Aware Ranking**.
6. Review concentration, invalidation, conflict, and allocation-headroom flags.

## Runtime

```text
market_forecaster/.local/portfolio/
├── state.json
└── latest_overlay.json
```

## API

Protected endpoints:

```text
GET  /api/v1/portfolio/state
POST /api/v1/portfolio/state

GET  /api/v1/portfolio/ranking
GET  /api/v1/portfolio/ranking/latest
```

Example state payload:

```json
{
  "cash": 10000,
  "positions": [
    {"ticker": "AAPL", "quantity": 20, "cost_basis": 205.50},
    {"ticker": "TMC", "quantity": 500, "cost_basis": 5.10}
  ]
}
```

## Install

Keep the extracted patch folder intact. It uses only the unique
`mf35_payload_v350` directory.

From repo root:

```powershell
python market_forecaster_v2_portfolio_patch_3.5.0\apply_portfolio_patch_3_5_0.py
python -m compileall -q market_forecaster
python -m pytest market_forecaster\tests\test_portfolio.py -q
streamlit run market_forecaster\app.py
```

## Next milestone

Recommended 3.6: trade-plan journal + realized execution analytics. Allow a user
to record a planned entry/stop/target and actual fills, then compare forecast
quality, decision quality, and execution quality separately.
