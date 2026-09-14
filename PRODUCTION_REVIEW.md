# Market Forecaster — Production Readiness Review & Refactoring Plan

**Reviewer:** Claude (Opus 4.6)  
**Date:** April 2, 2026  
**Codebase:** `app.py` (~5,500 LOC single file) + `DEV_HANDOFF.md`

---

## Executive Summary

The Market Forecaster has strong foundational capabilities — Prophet forecasting, ensemble models (ARIMA/RF/LSTM), options flow analysis, chart pattern detection, and a two-stage AutoTune system. However, the current codebase has critical production blockers: a monolithic 5,500-line single file, simulated sentiment data presented as real, data leakage risks in evaluation, and no structured API layer for integration with other tools. The app is roughly at **beta quality** — functional but not production-safe.

This document covers: (1) critical bugs to fix immediately, (2) architecture refactoring into modules, (3) accuracy improvements from the DEV_HANDOFF, (4) API-first design for integration, and (5) a phased sprint plan.

---

## 1. Critical Issues (Fix Before Any User Touches It)

### 1.1 Recursive Infinite Loop in `_st_rerun()`
```python
def _st_rerun():
    if hasattr(st, 'rerun'):
        st.rerun()
    else:
        _st_rerun()  # BUG: infinite recursion, should be st.experimental_rerun()
```
**Impact:** App crashes on older Streamlit versions. Fix: call `st.experimental_rerun()` in the else branch.

### 1.2 Sentiment Analysis Uses Fully Simulated Data
The `SentimentAnalyzer` class generates random numbers seeded by ticker+date. Headlines are hardcoded templates. This is presented to users as "Market Sentiment Analysis" with no disclaimer visible in the UI (only buried in the Help tab).

**Impact:** Users make trading decisions based on random noise labeled as sentiment data.  
**Fix:** Either (a) integrate a real sentiment API (Alpha Vantage News Sentiment, Finnhub, or a simple news scraper with TextBlob/VADER), or (b) prominently label it as "Simulated — Demo Only" in the tab header and every metric card.

### 1.3 Options Features Are Synthetic Historical Series
`create_options_features_timeseries()` takes a current snapshot and fabricates a historical time series with `np.random.seed(42)`. This synthetic data is then fed to Prophet as regressors.

**Impact:** The model learns from fabricated patterns that don't exist in reality. Forecasts using options features may be actively misleading.  
**Fix:** Use the options snapshot only for the *current* signal display. Do not feed synthetic history into Prophet. If historical options data is unavailable, disable the regressor — don't invent it.

### 1.4 Holdout Evaluation Leakage Risk
The `evaluate_on_holdout()` function merges forecast with actuals on the *full* prophet_df, then takes the `.tail(holdout_days)`. But `fit_and_forecast()` trains on the entire prophet_df (including the holdout window), then predicts forward.

The AutoTune's `_oos_holdout_metrics()` does this correctly (splits train/test), but the main forecast tab does not. Users see artificially good metrics.

**Fix:** The main evaluation should also use train/test splitting, or at minimum clearly label the metrics as "in-sample fit" vs "out-of-sample."

### 1.5 Bare `except:` Clauses Everywhere
~40+ instances of `except:` with no exception type, silently swallowing errors. This makes debugging nearly impossible.

**Fix:** Replace with `except Exception as e:` and log/display meaningful error context.

### 1.6 Duplicate Function Definition
`compute_trading_signal` is defined twice (lines 264 and ~line 1600+ equivalent). The second definition silently overwrites the first.

---

## 2. Architecture: From Monolith to Modules

The current 5,500-line single file is unmaintainable. Here's the target structure:

```
market_forecaster/
├── app.py                    # Streamlit entry point (~200 lines)
├── config.py                 # Plans, presets, constants, feature flags
├── core/
│   ├── __init__.py
│   ├── data.py               # fetch_stock_data, fetch_options_data
│   ├── indicators.py         # add_technical_indicators, TECH_FEATURE_COLUMNS
│   ├── patterns.py           # Chart pattern detection (all pattern functions)
│   ├── prophet_model.py      # prepare_for_prophet, fit_and_forecast, evaluate
│   ├── ensemble.py           # EnsembleForecaster (ARIMA, RF, LSTM)
│   ├── sentiment.py          # SentimentAnalyzer (real or clearly-labeled demo)
│   ├── seasonal.py           # SeasonalAnalyzer
│   └── signals.py            # compute_trading_signal, generate_integrated_signal
├── autotune/
│   ├── __init__.py
│   ├── tuner.py              # AutoTune logic (coarse + refine)
│   └── config_store.py       # Best-known config per ticker (JSON/SQLite)
├── ui/
│   ├── __init__.py
│   ├── sidebar.py            # Sidebar configuration rendering
│   ├── tab_forecast.py       # Forecast tab
│   ├── tab_ensemble.py       # Ensemble tab
│   ├── tab_sentiment.py      # Sentiment tab
│   ├── tab_seasonal.py       # Seasonal tab
│   ├── tab_backtest.py       # Backtest tab
│   ├── tab_patterns.py       # Chart Patterns tab
│   ├── tab_help.py           # Help tab
│   ├── plots.py              # plot_forecast_with_signals, plot_pattern_timeline
│   └── components.py         # Reusable UI components (badges, signal cards)
├── api/                      # REST API layer (FastAPI) for integration
│   ├── __init__.py
│   ├── main.py               # FastAPI app
│   ├── routes/
│   │   ├── forecast.py       # POST /forecast
│   │   ├── signals.py        # GET /signals/{ticker}
│   │   ├── patterns.py       # GET /patterns/{ticker}
│   │   └── health.py         # GET /health
│   └── schemas.py            # Pydantic models for request/response
├── tests/
│   ├── test_indicators.py
│   ├── test_patterns.py
│   ├── test_prophet_model.py
│   ├── test_ensemble.py
│   └── test_signals.py
├── requirements.txt
├── Dockerfile
└── README.md
```

### Why This Matters for Integration
Your DEV_HANDOFF mentions "easily integrated to other apps or tools." The current Streamlit-only architecture makes that impossible — all logic is tangled with UI code. Separating `core/` from `ui/` means:

- The `core/` modules can be imported by a FastAPI service, a CLI tool, a Jupyter notebook, or a scheduled job
- The `api/` layer exposes a clean REST interface for webhooks, mobile apps, or third-party dashboards
- Tests can validate forecast logic without spinning up Streamlit

---

## 3. Accuracy Improvements (From DEV_HANDOFF Sprint 1)

### 3.1 Multi-Metric Evaluation
Currently only MAE/RMSE/MAPE. Add:
- **sMAPE** (symmetric, handles near-zero prices better)
- **Directional Accuracy** (% of days where predicted direction matches actual)
- **MASE** (scale-free, good for cross-asset comparison)

### 3.2 AutoTune Scoring with Stability Penalty
Current: ranks by raw MAPE.  
Proposed: `score = mean_mape + 0.25 * std_mape`  
This penalizes configs that happen to score well on one fold but poorly on others.

### 3.3 Best-Known Config Store
Save winning AutoTune configs per ticker to a JSON file:
```json
{
  "AAPL": {
    "params": {"cps": 0.08, "sps": 6.0, "growth": "linear", ...},
    "metrics": {"mape": 2.3, "mape_std": 0.4, "folds": 3},
    "last_updated": "2026-04-01T12:00:00Z"
  }
}
```
Add "Load Best Known" and "Re-tune" buttons in the sidebar.

### 3.4 Validation-Weighted Ensemble
Current ensemble uses static weights. Better approach:
```python
weights = {model: 1.0 / max(error, 0.01) for model, error in validation_errors.items()}
total = sum(weights.values())
weights = {k: v/total for k, v in weights.items()}
```
Only use ensemble if it beats Prophet baseline on holdout.

---

## 4. API-First Design (For Integration)

### 4.1 FastAPI Endpoints

```
POST /api/v1/forecast
  Body: {ticker, period, horizon, options, model_config}
  Returns: {dates, forecast, lower, upper, metrics, signal}

GET /api/v1/signals/{ticker}
  Returns: {technical, patterns, options, ensemble, sentiment, seasonal, integrated}

GET /api/v1/patterns/{ticker}?period=1y
  Returns: {scores: {ascending_triangle: 0.7, ...}, bias: "Bullish"}

POST /api/v1/autotune
  Body: {ticker, budget, period}
  Returns: {best_config, leaderboard, metrics}

GET /api/v1/health
  Returns: {status, models_available, version}
```

### 4.2 Webhook Support
For integration with trading platforms or alerting systems:
```
POST /api/v1/webhooks
  Body: {url, events: ["signal_change", "pattern_detected"], tickers: ["AAPL"]}
```

---

## 5. UI Improvements (DEV_HANDOFF Sprint 2)

### 5.1 Mode Selector
Top of sidebar: **Simple** | **Trader** | **Analyst**

- **Simple**: Ticker + preset + Run. Show forecast chart + plain-English summary. Hide all advanced tabs.
- **Trader**: Add horizon/holdout, AutoTune, backtest, signal breakdown.
- **Analyst**: Full Prophet params, ensemble weights, pattern timeline, diagnostics.

### 5.2 Plain-English Interpretation Panel
After every forecast, show a card like:
> **AAPL — 30-Day Outlook**  
> The model expects a moderate uptrend (+3.2%) with medium confidence. RSI is neutral (52), options flow is slightly bullish. The ascending triangle pattern (score: 0.72) supports continuation. Risk: MAPE of 4.1% means the actual price could differ by ~$8 from the forecast.

### 5.3 Disclaimer / Risk Warning
For a financial product, every page should show:
> ⚠️ This tool is for educational and research purposes. It does not constitute financial advice. Past performance does not predict future results. Always do your own research before trading.

---

## 6. Sprint Plan

### Sprint 1 — Production Foundation (2 weeks)
- [ ] Fix critical bugs (recursive rerun, duplicate function, bare excepts)
- [ ] Refactor into modular structure (core/, ui/, config)
- [ ] Fix holdout evaluation leakage in main forecast tab
- [ ] Label simulated data clearly OR integrate real sentiment API
- [ ] Remove synthetic options history from Prophet regressors
- [ ] Add multi-metric evaluation (sMAPE, directional accuracy)
- [ ] Add stability penalty to AutoTune scoring
- [ ] Add best-known config store per ticker
- [ ] Add disclaimer/risk warning to all pages
- [ ] Write tests for core/ modules

### Sprint 2 — API Layer + Integration (2 weeks)
- [ ] Build FastAPI service wrapping core/ modules
- [ ] Define Pydantic schemas for all endpoints
- [ ] Add /forecast, /signals, /patterns, /autotune, /health endpoints
- [ ] Dockerize (Streamlit + FastAPI in single container or separate)
- [ ] Add webhook support for signal changes
- [ ] API key authentication for external consumers

### Sprint 3 — UI Polish + Onboarding (1 week)
- [ ] Implement Mode Selector (Simple/Trader/Analyst)
- [ ] Plain-English interpretation panel
- [ ] Progressive disclosure in sidebar
- [ ] Reduce tabs in Simple mode
- [ ] Mobile layout fixes

### Sprint 4 — Subscriptions + Auth (1 week)
- [ ] Stripe integration
- [ ] Server-side plan enforcement (not just query param)
- [ ] Usage limits + audit logging
- [ ] Saved runs / watchlist

---

## 7. Quick Wins (Do Today)

1. Fix `_st_rerun()` infinite loop
2. Add `⚠️ Simulated Data` badges to Sentiment tab
3. Replace bare `except:` with `except Exception as e:`
4. Remove duplicate `compute_trading_signal` definition
5. Add financial disclaimer to footer
6. Add `__version__` and health check endpoint

---

*This review is based on the codebase as of April 2, 2026. The DEV_HANDOFF priorities are well-aligned — this document adds the integration architecture and critical bug fixes that were missing.*
