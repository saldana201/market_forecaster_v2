"""Options Flow v2: current-chain analytics with explicit proxy labeling.

This module never fabricates historical options data. It analyzes current option
chains, optionally persists observed snapshots, and exposes features that can be
used by the signal/regime overlay layer. It does NOT infer true dealer inventory
or true trade direction from broker prints.
"""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

try:  # network/provider dependency is optional for pure analytics tests
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except Exception:  # pragma: no cover - environment dependent
    yf = None
    YFINANCE_AVAILABLE = False

_TICKER_RE = re.compile(r"^[A-Z0-9.^=_-]{1,24}$")
_BUCKETS = (
    ("0-7d", 0, 7),
    ("8-30d", 8, 30),
    ("31-60d", 31, 60),
    ("61-120d", 61, 120),
    ("121d+", 121, 10000),
)


@dataclass(frozen=True)
class OptionGreeks:
    delta: float
    gamma: float


def _normalize_ticker(ticker: str) -> str:
    value = str(ticker or "").upper().strip()
    if not value or not _TICKER_RE.fullmatch(value):
        raise ValueError("Invalid ticker symbol")
    return value


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def option_greeks(
    spot: float,
    strike: float,
    t_years: float,
    iv: float,
    side: str,
    *,
    risk_free_rate: float = 0.045,
    dividend_yield: float = 0.0,
) -> OptionGreeks:
    """Black-Scholes delta/gamma approximation from chain IV.

    The result is an approximation because chain IV, rates, dividends, and quote
    timestamps are provider-dependent. Gamma is mathematically positive for both
    calls and puts; any signed GEX built later is a heuristic sign convention.
    """
    s = float(spot)
    k = float(strike)
    t = max(float(t_years), 1.0 / 365.0)
    sigma = float(iv)
    if s <= 0 or k <= 0 or not np.isfinite(sigma) or sigma <= 0:
        return OptionGreeks(float("nan"), float("nan"))

    sqrt_t = math.sqrt(t)
    denom = sigma * sqrt_t
    if denom <= 0:
        return OptionGreeks(float("nan"), float("nan"))
    d1 = (math.log(s / k) + (risk_free_rate - dividend_yield + 0.5 * sigma * sigma) * t) / denom
    disc_q = math.exp(-dividend_yield * t)
    gamma = disc_q * _norm_pdf(d1) / (s * denom)
    side_u = str(side).upper()
    if side_u == "CALL":
        delta = disc_q * _norm_cdf(d1)
    elif side_u == "PUT":
        delta = -disc_q * _norm_cdf(-d1)
    else:
        raise ValueError("side must be CALL or PUT")
    return OptionGreeks(float(delta), float(gamma))


def _bucket_for_dte(dte: int) -> str:
    for name, lo, hi in _BUCKETS:
        if lo <= dte <= hi:
            return name
    return "121d+"


def _num(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(0.0, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def _weighted_mean(values: Iterable[float], weights: Iterable[float]) -> float:
    v = np.asarray(list(values), dtype=float)
    w = np.asarray(list(weights), dtype=float)
    mask = np.isfinite(v) & np.isfinite(w) & (w > 0)
    if not mask.any():
        return float("nan")
    return float(np.average(v[mask], weights=w[mask]))


def _finite(value, default=0.0) -> float:
    try:
        v = float(value)
    except Exception:
        return float(default)
    return v if np.isfinite(v) else float(default)


def _new_bucket(name: str) -> dict:
    return {
        "bucket": name,
        "contracts": 0,
        "call_volume": 0.0,
        "put_volume": 0.0,
        "call_oi": 0.0,
        "put_oi": 0.0,
        "call_gamma_dollar_1pct": 0.0,
        "put_gamma_dollar_1pct": 0.0,
        "signed_gamma_proxy": 0.0,
        "classified_pressure_notional": 0.0,
        "gross_pressure_notional": 0.0,
        "total_volume": 0.0,
        "classified_volume": 0.0,
        "atm_iv_values": [],
        "atm_iv_weights": [],
        "call25_iv_values": [],
        "call25_iv_weights": [],
        "put25_iv_values": [],
        "put25_iv_weights": [],
        "dtes": [],
    }


def _quote_aggressor(bid: float, ask: float, last: float) -> int:
    """Approximate quote-side aggressor: +1 buyer, -1 seller, 0 unclassified."""
    if bid <= 0 or ask <= bid or last <= 0:
        return 0
    spread = ask - bid
    midpoint = (ask + bid) / 2.0
    band = max(0.05 * spread, 0.005)
    if last >= midpoint + band:
        return 1
    if last <= midpoint - band:
        return -1
    return 0


def _finalize_bucket(raw: dict) -> dict:
    atm_iv = _weighted_mean(raw["atm_iv_values"], raw["atm_iv_weights"])
    call25 = _weighted_mean(raw["call25_iv_values"], raw["call25_iv_weights"])
    put25 = _weighted_mean(raw["put25_iv_values"], raw["put25_iv_weights"])
    skew = put25 - call25 if np.isfinite(put25) and np.isfinite(call25) else float("nan")
    gross = float(raw["gross_pressure_notional"])
    pressure = float(raw["classified_pressure_notional"] / gross) if gross > 0 else 0.0
    total_vol = float(raw["total_volume"])
    coverage = float(raw["classified_volume"] / total_vol) if total_vol > 0 else 0.0
    dtes = raw["dtes"]
    return {
        "bucket": raw["bucket"],
        "median_dte": float(np.median(dtes)) if dtes else None,
        "contracts": int(raw["contracts"]),
        "call_volume": int(raw["call_volume"]),
        "put_volume": int(raw["put_volume"]),
        "call_oi": int(raw["call_oi"]),
        "put_oi": int(raw["put_oi"]),
        "put_call_volume_ratio": float(raw["put_volume"] / max(raw["call_volume"], 1.0)),
        "put_call_oi_ratio": float(raw["put_oi"] / max(raw["call_oi"], 1.0)),
        "call_gamma_dollar_1pct": float(raw["call_gamma_dollar_1pct"]),
        "put_gamma_dollar_1pct": float(raw["put_gamma_dollar_1pct"]),
        "signed_gamma_proxy": float(raw["signed_gamma_proxy"]),
        "atm_iv": float(atm_iv) if np.isfinite(atm_iv) else None,
        "call_25d_iv": float(call25) if np.isfinite(call25) else None,
        "put_25d_iv": float(put25) if np.isfinite(put25) else None,
        "skew_25d": float(skew) if np.isfinite(skew) else None,
        "directional_pressure_score": float(np.clip(pressure, -1, 1)),
        "pressure_coverage": float(np.clip(coverage, 0, 1)),
    }


def analyze_options_frames(
    expirations_data: Iterable[dict],
    *,
    spot: float,
    ticker: str = "TEST",
    as_of: datetime | None = None,
    risk_free_rate: float = 0.045,
    dividend_yield: float = 0.0,
) -> dict:
    """Analyze already-fetched option-chain frames without network access."""
    symbol = _normalize_ticker(ticker)
    spot = float(spot)
    if spot <= 0:
        raise ValueError("spot must be positive")
    now = as_of or datetime.now(timezone.utc)
    now_date = pd.Timestamp(now).date()

    buckets = {name: _new_bucket(name) for name, _, _ in _BUCKETS}
    unusual: list[dict] = []
    total_abs_gamma = 0.0
    total_signed_gamma = 0.0
    total_call_vol = total_put_vol = total_call_oi = total_put_oi = 0.0
    total_pressure_signed = total_pressure_gross = 0.0
    total_volume = classified_volume = 0.0
    analyzed = 0

    for item in expirations_data:
        expiry_text = str(item.get("expiry", ""))
        try:
            expiry_date = pd.Timestamp(expiry_text).date()
        except Exception:
            continue
        dte = max((expiry_date - now_date).days, 0)
        bucket_name = _bucket_for_dte(dte)
        bucket = buckets[bucket_name]
        bucket["dtes"].append(dte)
        t_years = max(dte, 1) / 365.0

        for side, frame in (("CALL", item.get("calls")), ("PUT", item.get("puts"))):
            if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
                continue
            frame = frame.copy()
            strikes = _num(frame, "strike")
            volume = _num(frame, "volume")
            oi = _num(frame, "openInterest")
            ivs = _num(frame, "impliedVolatility")
            bids = _num(frame, "bid")
            asks = _num(frame, "ask")
            lasts = _num(frame, "lastPrice")
            side_dir = 1.0 if side == "CALL" else -1.0

            if side == "CALL":
                total_call_vol += float(volume.sum())
                total_call_oi += float(oi.sum())
                bucket["call_volume"] += float(volume.sum())
                bucket["call_oi"] += float(oi.sum())
            else:
                total_put_vol += float(volume.sum())
                total_put_oi += float(oi.sum())
                bucket["put_volume"] += float(volume.sum())
                bucket["put_oi"] += float(oi.sum())

            for idx in frame.index:
                strike = _finite(strikes.loc[idx])
                if strike <= 0:
                    continue
                vol = max(_finite(volume.loc[idx]), 0.0)
                open_interest = max(_finite(oi.loc[idx]), 0.0)
                iv = _finite(ivs.loc[idx], float("nan"))
                bid = max(_finite(bids.loc[idx]), 0.0)
                ask = max(_finite(asks.loc[idx]), 0.0)
                last = max(_finite(lasts.loc[idx]), 0.0)
                total_volume += vol
                bucket["total_volume"] += vol
                bucket["contracts"] += 1
                analyzed += 1

                greeks = option_greeks(
                    spot, strike, t_years, iv, side,
                    risk_free_rate=risk_free_rate,
                    dividend_yield=dividend_yield,
                )
                if np.isfinite(greeks.gamma):
                    gamma_dollar = greeks.gamma * open_interest * 100.0 * spot * spot * 0.01
                    total_abs_gamma += abs(gamma_dollar)
                    signed = side_dir * gamma_dollar
                    total_signed_gamma += signed
                    bucket["signed_gamma_proxy"] += signed
                    if side == "CALL":
                        bucket["call_gamma_dollar_1pct"] += gamma_dollar
                    else:
                        bucket["put_gamma_dollar_1pct"] += gamma_dollar

                # IV surface slices: 5% ATM and approximately 25-delta wings.
                if np.isfinite(iv) and 0.01 <= iv <= 5.0:
                    iv_weight = max(open_interest + vol, 1.0)
                    if abs(strike / spot - 1.0) <= 0.05:
                        bucket["atm_iv_values"].append(iv)
                        bucket["atm_iv_weights"].append(iv_weight)
                    if np.isfinite(greeks.delta):
                        if side == "CALL" and 0.15 <= greeks.delta <= 0.35:
                            bucket["call25_iv_values"].append(iv)
                            bucket["call25_iv_weights"].append(iv_weight)
                        elif side == "PUT" and -0.35 <= greeks.delta <= -0.15:
                            bucket["put25_iv_values"].append(iv)
                            bucket["put25_iv_weights"].append(iv_weight)

                aggressor = _quote_aggressor(bid, ask, last)
                if aggressor != 0 and vol > 0:
                    midpoint = (bid + ask) / 2.0 if ask > bid > 0 else 0.0
                    premium = last if last > 0 else midpoint
                    notional = vol * 100.0 * max(premium, 0.0)
                    directional = side_dir * aggressor * notional
                    total_pressure_signed += directional
                    total_pressure_gross += abs(notional)
                    classified_volume += vol
                    bucket["classified_pressure_notional"] += directional
                    bucket["gross_pressure_notional"] += abs(notional)
                    bucket["classified_volume"] += vol

                if open_interest > 100 and vol > 2.0 * open_interest:
                    unusual.append({
                        "side": side,
                        "strike": float(strike),
                        "expiry": expiry_text,
                        "dte": int(dte),
                        "volume": int(vol),
                        "open_interest": int(open_interest),
                        "vol_oi_ratio": float(vol / open_interest) if open_interest else 0.0,
                        "iv": float(iv) if np.isfinite(iv) else None,
                        "delta": float(greeks.delta) if np.isfinite(greeks.delta) else None,
                        "quote_aggressor_proxy": "BUY" if aggressor > 0 else "SELL" if aggressor < 0 else "UNCLASSIFIED",
                    })

    finalized = [_finalize_bucket(buckets[name]) for name, _, _ in _BUCKETS]
    nonempty = [b for b in finalized if b["contracts"] > 0]

    # Overall IV level is OI-weighted from maturity buckets.
    atm_values, atm_weights = [], []
    for b in nonempty:
        if b["atm_iv"] is not None:
            atm_values.append(b["atm_iv"])
            atm_weights.append(max(b["call_oi"] + b["put_oi"], 1))
    atm_iv = _weighted_mean(atm_values, atm_weights)

    # Prefer a front/near-term 25-delta skew; otherwise use the first available.
    skew_25d = float("nan")
    for b in nonempty:
        if b["skew_25d"] is not None and (b["median_dte"] or 999) <= 60:
            skew_25d = float(b["skew_25d"])
            break
    if not np.isfinite(skew_25d):
        candidates = [b["skew_25d"] for b in nonempty if b["skew_25d"] is not None]
        if candidates:
            skew_25d = float(candidates[0])

    iv_buckets = [b for b in nonempty if b["atm_iv"] is not None]
    term_slope = float("nan")
    if len(iv_buckets) >= 2:
        term_slope = float(iv_buckets[-1]["atm_iv"] - iv_buckets[0]["atm_iv"])

    pressure = total_pressure_signed / total_pressure_gross if total_pressure_gross > 0 else 0.0
    pressure_coverage = classified_volume / total_volume if total_volume > 0 else 0.0
    gamma_balance = total_signed_gamma / total_abs_gamma if total_abs_gamma > 0 else 0.0
    skew_component = -np.clip((skew_25d if np.isfinite(skew_25d) else 0.0) / 0.20, -1, 1)
    term_component = np.clip((term_slope if np.isfinite(term_slope) else 0.0) / 0.20, -1, 1)
    options_signal = float(np.clip(
        0.55 * pressure + 0.15 * gamma_balance + 0.20 * skew_component + 0.10 * term_component,
        -1, 1,
    ))

    if options_signal >= 0.35:
        state = "BULLISH_FLOW"
        overlay = "RISK_ON"
    elif options_signal <= -0.35:
        state = "BEARISH_FLOW"
        overlay = "RISK_OFF"
    else:
        state = "BALANCED"
        overlay = "NEUTRAL"
    if (
        np.isfinite(skew_25d) and skew_25d >= 0.12
        and np.isfinite(term_slope) and term_slope <= -0.05
        and pressure <= -0.15
    ):
        state = "STRESS_RISK"
        overlay = "VOLATILITY_WARNING"

    if pressure_coverage < 0.15:
        confidence = "LOW"
    elif pressure_coverage < 0.40:
        confidence = "MEDIUM"
    else:
        confidence = "HIGH"

    unusual = sorted(unusual, key=lambda x: (x["vol_oi_ratio"], x["volume"]), reverse=True)[:20]
    return {
        "schema_version": 2,
        "available": analyzed > 0,
        "ticker": symbol,
        "spot": float(spot),
        "as_of_utc": now.astimezone(timezone.utc).isoformat(),
        "provider": "yfinance" if symbol != "TEST" else "synthetic-test",
        "contracts_analyzed": int(analyzed),
        "put_call_volume_ratio": float(total_put_vol / max(total_call_vol, 1.0)),
        "put_call_oi_ratio": float(total_put_oi / max(total_call_oi, 1.0)),
        "atm_iv": float(atm_iv) if np.isfinite(atm_iv) else None,
        "skew_25d": float(skew_25d) if np.isfinite(skew_25d) else None,
        "iv_term_structure_slope": float(term_slope) if np.isfinite(term_slope) else None,
        "signed_gamma_proxy": float(total_signed_gamma),
        "gamma_balance_score": float(np.clip(gamma_balance, -1, 1)),
        "directional_pressure_score": float(np.clip(pressure, -1, 1)),
        "pressure_coverage": float(np.clip(pressure_coverage, 0, 1)),
        "pressure_confidence": confidence,
        "options_signal_score": options_signal,
        "options_state": state,
        "regime_overlay": overlay,
        "maturity_buckets": finalized,
        "unusual_activity": unusual,
        "assumptions": {
            "risk_free_rate": float(risk_free_rate),
            "dividend_yield": float(dividend_yield),
            "signed_gamma": "CALL gamma positive / PUT gamma negative heuristic; not dealer inventory",
            "directional_pressure": "last trade vs bid/ask midpoint proxy; not a true order-flow aggressor feed",
            "iv_surface": "Black-Scholes delta/gamma approximation using provider IV",
        },
        "routing_policy": "display_and_signal_only_until_observed_snapshot_history_is_sufficient",
    }


def fetch_options_flow_v2(
    ticker: str,
    *,
    spot: float | None = None,
    max_expiries: int = 12,
    risk_free_rate: float | None = None,
    dividend_yield: float = 0.0,
) -> dict:
    """Fetch and analyze a current options snapshot from yfinance."""
    if not YFINANCE_AVAILABLE:
        raise RuntimeError("yfinance is not installed")
    symbol = _normalize_ticker(ticker)
    max_expiries = int(np.clip(max_expiries, 1, 24))
    if risk_free_rate is None:
        risk_free_rate = float(os.getenv("MARKET_FORECASTER_RISK_FREE_RATE", "0.045"))

    stock = yf.Ticker(symbol)
    expiries = tuple(stock.options or ())[:max_expiries]
    if not expiries:
        return {
            "schema_version": 2,
            "available": False,
            "ticker": symbol,
            "provider": "yfinance",
            "as_of_utc": datetime.now(timezone.utc).isoformat(),
            "reason": "No listed option expirations returned by provider",
        }

    resolved_spot = _finite(spot, 0.0)
    if resolved_spot <= 0:
        try:
            resolved_spot = _finite(stock.fast_info.get("last_price"), 0.0)
        except Exception:
            resolved_spot = 0.0
    if resolved_spot <= 0:
        hist = stock.history(period="5d", auto_adjust=False)
        if not hist.empty:
            resolved_spot = float(pd.to_numeric(hist["Close"], errors="coerce").dropna().iloc[-1])
    if resolved_spot <= 0:
        raise RuntimeError("Unable to resolve current underlying price")

    chains: list[dict] = []
    skipped = 0
    for expiry in expiries:
        try:
            chain = stock.option_chain(expiry)
            chains.append({"expiry": expiry, "calls": chain.calls, "puts": chain.puts})
        except Exception:
            skipped += 1

    result = analyze_options_frames(
        chains,
        spot=resolved_spot,
        ticker=symbol,
        risk_free_rate=float(risk_free_rate),
        dividend_yield=float(dividend_yield),
    )
    result["expirations_requested"] = len(expiries)
    result["expirations_loaded"] = len(chains)
    result["expirations_skipped"] = skipped
    result["provider"] = "yfinance"
    return result


def _default_store_dir() -> Path:
    override = os.getenv("MARKET_FORECASTER_OPTIONS_HISTORY_DIR")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[1] / ".local" / "options_flow"


def persist_options_snapshot(snapshot: dict, base_dir: str | Path | None = None) -> Path | None:
    """Append one real observed snapshot as JSONL; synthetic history is never created."""
    if not snapshot or not snapshot.get("available"):
        return None
    ticker = _normalize_ticker(snapshot.get("ticker", ""))
    directory = Path(base_dir) if base_dir is not None else _default_store_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{ticker}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, sort_keys=True, default=str) + "\n")
    return path


def load_options_history(
    ticker: str,
    *,
    base_dir: str | Path | None = None,
    limit: int = 250,
) -> list[dict]:
    symbol = _normalize_ticker(ticker)
    directory = Path(base_dir) if base_dir is not None else _default_store_dir()
    path = directory / f"{symbol}.jsonl"
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-max(1, int(limit)):]


def derive_options_regime_overlay(options_data: dict, base_regime: str | None = None) -> dict:
    """Return a non-routing options overlay for the current causal regime.

    The overlay intentionally does not alter learned model-routing weights because
    the application does not yet possess enough historical options snapshots to
    validate such routing out of sample.
    """
    if not options_data or not options_data.get("available"):
        return {
            "base_regime": base_regime,
            "options_overlay": "UNAVAILABLE",
            "options_state": "UNAVAILABLE",
            "risk_score": 0.0,
            "routing_effect": "NONE",
        }
    score = float(np.clip(options_data.get("options_signal_score", 0.0), -1, 1))
    return {
        "base_regime": base_regime,
        "options_overlay": options_data.get("regime_overlay", "NEUTRAL"),
        "options_state": options_data.get("options_state", "BALANCED"),
        "risk_score": score,
        "routing_effect": "DISPLAY_AND_SIGNAL_ONLY",
        "reason": "Model routing waits for sufficient observed options snapshot history and OOS validation",
    }
