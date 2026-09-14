# Market Forecaster v2.0

**OneEight AI Systems** — Multi-model market forecasting platform.

## Architecture

```
market_forecaster/
├── app.py                 # Streamlit entry point (mode selector UI)
├── config.py              # Plans, presets, constants, feature flags
├── core/                  # Pure logic — no UI dependency
│   ├── data.py            # Stock + options data fetching
│   ├── indicators.py      # Technical indicators (RSI, MACD, SMA, etc.)
│   ├── patterns.py        # Chart pattern detection (16 patterns)
│   ├── prophet_model.py   # Prophet fit, forecast, OOS evaluation
│   ├── ensemble.py        # ARIMA + Random Forest + LSTM ensemble
│   ├── signals.py         # Trading signal generation
│   ├── sentiment.py       # Sentiment analysis (simulated / real API hook)
│   └── seasonal.py        # Seasonal & earnings patterns
├── autotune/
│   ├── tuner.py           # Two-stage AutoTune with stability penalty
│   └── config_store.py    # Best-known config persistence (JSON)
├── ui/                    # Streamlit UI layer
│   ├── sidebar.py         # Mode selector + progressive disclosure
│   ├── components.py      # Signal cards, badges, disclaimers
│   ├── plots.py           # Plotly charts (forecast, ensemble, seasonal)
│   └── insights.py        # Plain-English interpretation engine
├── api/                   # FastAPI REST service
│   ├── main.py            # App entry point
│   ├── schemas.py         # Pydantic request/response models
│   └── routes/
│       ├── forecast.py    # POST /api/v1/forecast
│       ├── signals.py     # GET /api/v1/signals/{ticker}
│       ├── patterns.py    # GET /api/v1/patterns/{ticker}
│       └── autotune.py    # POST + GET /api/v1/autotune
├── tests/                 # pytest test suite
├── requirements.txt
└── Dockerfile
```

## Quick Start

### Install
```bash
pip install -r market_forecaster/requirements.txt
```

### Run Streamlit (new UI with mode selector)
From the directory that **contains** `market_forecaster/`:
```bash
streamlit run market_forecaster/app.py
```

### Run API
From the same directory:
```bash
uvicorn market_forecaster.api.main:app --reload --port 8000
# Docs at http://localhost:8000/docs
```

### Run Tests
```bash
pytest market_forecaster/tests/ -v
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/forecast` | Run complete forecast for a ticker |
| `GET` | `/api/v1/signals/{ticker}` | Get current trading signals |
| `GET` | `/api/v1/patterns/{ticker}` | Get chart pattern analysis |
| `POST` | `/api/v1/autotune` | Find optimal Prophet config |
| `GET` | `/api/v1/autotune/{ticker}` | Retrieve best-known config |
| `GET` | `/api/v1/health` | Service health + model availability |

### Example: Run a forecast
```bash
curl -X POST http://localhost:8000/api/v1/forecast \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "AAPL",
    "period": "1y",
    "horizon": 30,
    "use_ensemble": true
  }'
```

### Example: Get signals
```bash
curl "http://localhost:8000/api/v1/signals/AAPL?include_ensemble=true&include_seasonal=true"
```

## Integration

The `core/` package has zero UI dependencies — import directly:

```python
from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.indicators import add_technical_indicators
from market_forecaster.core.patterns import detect_chart_patterns
from market_forecaster.core.signals import compute_basic_signal

# Fetch and analyze
df = fetch_stock_data("AAPL", "1y", "1d")
df = add_technical_indicators(df)
patterns = detect_chart_patterns(df)

# Use in your own pipeline, webhook, scheduler, etc.
```

## Key Improvements over v1

1. **Modular architecture** — core logic separated from UI
2. **REST API** — FastAPI service for integration with any tool
3. **Fixed holdout evaluation** — proper train/test separation
4. **Multi-metric evaluation** — MAE, RMSE, MAPE, sMAPE, directional accuracy
5. **Stability scoring** — AutoTune penalizes unstable configs
6. **Best-known config store** — persist optimal settings per ticker
7. **Simulated data labeled** — sentiment flagged as `is_simulated: true`
8. **No synthetic options history** — options snapshot used for display only
9. **No bare except clauses** — proper error handling throughout
10. **Typed dataclasses** — `ForecastRequest`, `SignalResult` for validated configs

## Disclaimer

⚠️ This tool is for educational and research purposes only. It does not
constitute financial advice. Past performance does not guarantee future
results. Always do your own research before making trading decisions.
