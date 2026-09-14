"""
Market Forecaster — Best-Known Config Store
Persist and retrieve optimal AutoTune configurations per ticker.
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_STORE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else ".",
    "..", "best_configs.json"
)


class ConfigStore:
    """Simple JSON-based store for best-known forecast configurations."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or DEFAULT_STORE_PATH
        self._data = self._load()

    def _load(self) -> dict:
        try:
            if os.path.exists(self.path):
                with open(self.path, "r") as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"Failed to load config store: {e}")
        return {}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            with open(self.path, "w") as f:
                json.dump(self._data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save config store: {e}")

    def get(self, ticker: str) -> Optional[dict]:
        """Get best-known config for a ticker."""
        return self._data.get(ticker.upper())

    def save(self, ticker: str, params: dict, metrics: dict):
        """Save a new best config for a ticker."""
        self._data[ticker.upper()] = {
            "params": params,
            "metrics": metrics,
            "last_updated": datetime.utcnow().isoformat(),
        }
        self._save()

    def delete(self, ticker: str):
        """Remove a ticker's config."""
        self._data.pop(ticker.upper(), None)
        self._save()

    def list_tickers(self) -> list:
        """List all tickers with stored configs."""
        return sorted(self._data.keys())

    def is_stale(self, ticker: str, max_age_days: int = 7) -> bool:
        """Check if a stored config is older than max_age_days."""
        entry = self.get(ticker)
        if not entry or "last_updated" not in entry:
            return True
        try:
            updated = datetime.fromisoformat(entry["last_updated"])
            age = (datetime.utcnow() - updated).days
            return age > max_age_days
        except Exception:
            return True
