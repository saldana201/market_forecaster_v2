# Market Forecaster 2.6.0 — Options Flow v2

This release is built against the GitHub `master` baseline containing the 2.5 Production Consensus stack.

## What it adds

- Maturity-bucketed option-chain analytics: `0-7d`, `8-30d`, `31-60d`, `61-120d`, and `121d+`.
- Black-Scholes delta/gamma approximations using provider implied volatility.
- Call/put gamma-dollar exposure by maturity plus an explicitly labeled **signed gamma proxy**.
- Quote-side directional pressure proxy based on last trade versus bid/ask midpoint.
- Pressure-coverage score so weak quote classification is visible instead of hidden.
- ATM IV, approximate 25-delta call/put IV, downside skew, and IV term-structure slope.
- Options state / regime overlay (`RISK_ON`, `RISK_OFF`, `VOLATILITY_WARNING`, `NEUTRAL`).
- Current Options Flow v2 score can contribute to the integrated trading signal.
- Observed snapshots are appended to `.local/options_flow/<TICKER>.jsonl` whenever Options Flow is enabled in Streamlit.
- No synthetic historical options series are created.
- New protected endpoint: `GET /api/v1/options/{ticker}`.
- New Options Flow v2 panel in the Ensemble tab.

## Production guardrail

Yahoo option chains do **not** reveal known dealer inventory or a true broker trade-aggressor flag. Therefore:

- `signed_gamma_proxy` uses a call-positive / put-negative sign convention and is **not** presented as dealer GEX.
- directional pressure uses last-price versus quote midpoint and is **not** presented as true order-flow direction.
- the options overlay may influence the current integrated signal, but it does **not** alter learned model-routing weights yet.
- model routing waits until enough real observed snapshots exist to perform out-of-sample historical validation.

## Install

Extract this patch folder directly inside your `market_forecaster_v2` repository root. You should have:

```text
market_forecaster_v2/
├── market_forecaster/
└── market_forecaster_v2_options_flow_patch_2.6.0/
    ├── apply_options_flow_patch_2_6_0.py
    ├── OPTIONS_FLOW_PATCH_README.md
    └── payload/
```

From the repo root:

```bash
python market_forecaster_v2_options_flow_patch_2.6.0/apply_options_flow_patch_2_6_0.py
python -m compileall -q market_forecaster
pytest market_forecaster/tests/test_options_flow_v2.py -q
streamlit run market_forecaster/app.py
```

No new Python package is required; this uses the existing pandas/numpy/yfinance stack.

Optional rate assumption override:

```bash
export MARKET_FORECASTER_RISK_FREE_RATE=0.045
```

On PowerShell:

```powershell
$env:MARKET_FORECASTER_RISK_FREE_RATE="0.045"
```

## Workflow

1. Enable **Options Flow** in the sidebar.
2. Run a forecast on an optionable equity/ETF.
3. Open **Ensemble → Options Flow v2**.
4. Review flow pressure, IV skew/term structure, gamma balance, maturity buckets, and unusual volume/OI candidates.
5. Each run persists a real observed snapshot locally for future validation work.

Crypto pairs such as `ETH-USD` generally do not expose listed Yahoo equity-style option chains and may return no options data.
