"""
Market Forecaster — Ensemble Forecasting
ARIMA + Random Forest + LSTM with validation-weighted blending.
"""

import logging
from datetime import timedelta
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import MinMaxScaler, StandardScaler

logger = logging.getLogger(__name__)

# Optional heavy dependencies
try:
    from statsmodels.tsa.arima.model import ARIMA
    ARIMA_AVAILABLE = True
except ImportError:
    ARIMA_AVAILABLE = False

try:
    import tensorflow as tf
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM as KerasLSTM, Dense, Dropout
    from tensorflow.keras.callbacks import EarlyStopping
    tf.get_logger().setLevel("ERROR")
    LSTM_AVAILABLE = True
except ImportError:
    LSTM_AVAILABLE = False


class EnsembleForecaster:
    """Ensemble of ARIMA, Random Forest, and LSTM with validation-weighted blending."""

    def __init__(self, weights: Optional[dict] = None):
        self.initial_weights = weights or {"arima": 0.25, "rf": 0.35, "lstm": 0.40}
        self.arima_model = None
        self.rf_model = None
        self.lstm_model = None
        self.scaler = MinMaxScaler()
        self.rf_scaler = StandardScaler()
        self.lookback = 20
        self.lstm_lookback = 60
        self.rf_last_values = None
        self.lstm_last_seq = None
        self._validation_errors = {}

    # --- Fit methods ---

    def fit_arima(self, series: pd.Series, order: tuple = (5, 1, 0)):
        if not ARIMA_AVAILABLE:
            return None
        try:
            clean = series.dropna()
            if len(clean) < 30:
                return None
            model = ARIMA(clean, order=order)
            self.arima_model = model.fit()
            return self.arima_model
        except Exception as e:
            logger.debug(f"ARIMA fit failed: {e}")
            return None

    def fit_rf(self, series: pd.Series):
        try:
            clean = series.dropna().values
            if len(clean) < self.lookback + 10:
                return None

            X, y = [], []
            for i in range(self.lookback, len(clean)):
                X.append(clean[i - self.lookback:i])
                y.append(clean[i])

            X, y = np.array(X), np.array(y)
            X_scaled = self.rf_scaler.fit_transform(X)

            self.rf_model = RandomForestRegressor(
                n_estimators=100, max_depth=10,
                min_samples_split=5, random_state=42, n_jobs=-1,
            )
            self.rf_model.fit(X_scaled, y)
            self.rf_last_values = clean[-self.lookback:]
            return self.rf_model
        except Exception as e:
            logger.debug(f"RF fit failed: {e}")
            return None

    def fit_lstm(self, series: pd.Series):
        if not LSTM_AVAILABLE:
            return None
        try:
            clean = series.dropna().values.reshape(-1, 1)
            if len(clean) < self.lstm_lookback + 20:
                return None

            scaled = self.scaler.fit_transform(clean)
            X, y = [], []
            for i in range(self.lstm_lookback, len(scaled)):
                X.append(scaled[i - self.lstm_lookback:i, 0])
                y.append(scaled[i, 0])

            X, y = np.array(X), np.array(y)
            X = X.reshape((X.shape[0], X.shape[1], 1))

            model = Sequential([
                KerasLSTM(50, return_sequences=True, input_shape=(X.shape[1], 1)),
                Dropout(0.2),
                KerasLSTM(50, return_sequences=False),
                Dropout(0.2),
                Dense(25),
                Dense(1),
            ])
            model.compile(optimizer="adam", loss="mean_squared_error")
            early_stop = EarlyStopping(monitor="loss", patience=5, restore_best_weights=True)
            model.fit(X, y, epochs=50, batch_size=32, callbacks=[early_stop], verbose=0)

            self.lstm_model = model
            self.lstm_last_seq = scaled[-self.lstm_lookback:]
            return self.lstm_model
        except Exception as e:
            logger.debug(f"LSTM fit failed: {e}")
            return None

    def fit_all(self, series: pd.Series):
        self.fit_arima(series)
        self.fit_rf(series)
        if LSTM_AVAILABLE:
            self.fit_lstm(series)
        return self

    # --- Predict methods ---

    def predict_arima(self, steps: int) -> Optional[np.ndarray]:
        if self.arima_model is None:
            return None
        try:
            return np.array(self.arima_model.forecast(steps=steps))
        except Exception:
            return None

    def predict_rf(self, steps: int) -> Optional[np.ndarray]:
        if self.rf_model is None or self.rf_last_values is None:
            return None
        try:
            preds = []
            current = self.rf_last_values.copy()
            for _ in range(steps):
                X = current[-self.lookback:].reshape(1, -1)
                X_scaled = self.rf_scaler.transform(X)
                pred = self.rf_model.predict(X_scaled)[0]
                preds.append(pred)
                current = np.append(current, pred)
            return np.array(preds)
        except Exception:
            return None

    def predict_lstm(self, steps: int) -> Optional[np.ndarray]:
        if self.lstm_model is None or self.lstm_last_seq is None:
            return None
        try:
            preds = []
            seq = self.lstm_last_seq.copy()
            for _ in range(steps):
                X = seq.reshape((1, self.lstm_lookback, 1))
                pred = self.lstm_model.predict(X, verbose=0)[0, 0]
                preds.append(pred)
                seq = np.append(seq[1:], [[pred]], axis=0)

            preds = np.array(preds).reshape(-1, 1)
            return self.scaler.inverse_transform(preds).flatten()
        except Exception:
            return None

    def predict_ensemble(self, steps: int, use_validation_weights: bool = True) -> tuple:
        """
        Generate ensemble prediction.

        If use_validation_weights=True and validation errors are available,
        weight models by 1/error (better models get more weight).
        """
        predictions = {}

        for name, predict_fn in [
            ("arima", self.predict_arima),
            ("rf", self.predict_rf),
            ("lstm", self.predict_lstm),
        ]:
            pred = predict_fn(steps)
            if pred is not None and len(pred) == steps:
                predictions[name] = pred

        if not predictions:
            return None, predictions

        # Determine weights
        if use_validation_weights and self._validation_errors:
            weights = {}
            for model in predictions:
                err = self._validation_errors.get(model, 1.0)
                weights[model] = 1.0 / max(err, 0.01)
            total = sum(weights.values())
            weights = {k: v / total for k, v in weights.items()}
        else:
            weights = self.initial_weights

        # Weighted average
        ensemble = np.zeros(steps)
        total_w = 0
        for model, pred in predictions.items():
            w = weights.get(model, 1 / len(predictions))
            ensemble += w * pred
            total_w += w

        if total_w > 0:
            ensemble /= total_w

        return ensemble, predictions

    def get_confidence_intervals(self, predictions: dict, ensemble: np.ndarray) -> tuple:
        if len(predictions) < 2:
            return ensemble * 0.95, ensemble * 1.05
        all_preds = np.stack(list(predictions.values()))
        std = np.std(all_preds, axis=0)
        return ensemble - 1.96 * std, ensemble + 1.96 * std


def run_ensemble_forecast(
    ticker: str,
    stock_df: pd.DataFrame,
    horizon: int,
    weights: Optional[dict] = None,
) -> Optional[dict]:
    """High-level ensemble forecast runner."""
    from market_forecaster.core.data import get_close_series

    close = get_close_series(stock_df)
    if close.empty:
        return None

    forecaster = EnsembleForecaster(weights=weights)
    forecaster.fit_all(close)

    ensemble, individual = forecaster.predict_ensemble(horizon)
    if ensemble is None:
        return None

    lower, upper = forecaster.get_confidence_intervals(individual, ensemble)

    last_date = stock_df["Date"].max() if "Date" in stock_df.columns else pd.Timestamp.now()
    future_dates = pd.date_range(start=last_date + timedelta(days=1), periods=horizon, freq="D")

    return {
        "ensemble": ensemble,
        "individual": individual,
        "lower": lower,
        "upper": upper,
        "dates": future_dates,
        "models_used": list(individual.keys()),
    }
