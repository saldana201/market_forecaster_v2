"""
Market Forecaster — Chart Pattern Detection
Rule-based detection of classical chart patterns (continuation + reversal).
Each detector returns a score from 0.0 (not detected) to 1.0 (strong textbook pattern).
"""

import numpy as np
import pandas as pd

from market_forecaster.config import PATTERN_FEATURE_COLUMNS


def _line_slope(arr: np.ndarray) -> float:
    """Approximate slope via linear regression."""
    arr = np.asarray(arr, dtype="float64").ravel()
    if arr.size < 2:
        return 0.0
    x = np.arange(arr.size, dtype="float64")
    m, _ = np.polyfit(x, arr, 1)
    return float(m)


def _to_score(val) -> float:
    """Safely convert to a [0, 1] score."""
    v = np.asarray(val, dtype="float64")
    scalar = float(v.ravel()[0]) if v.size > 0 else 0.0
    return float(round(max(0.0, min(scalar, 1.0)), 2))


def _find_swings(df: pd.DataFrame, lookback: int = 5) -> pd.DataFrame:
    """Identify swing highs/lows using fixed lookback."""
    df = df.copy()
    if "High" not in df.columns or "Low" not in df.columns:
        return df
    df["swing_high"] = df["High"][
        (df["High"].shift(lookback) < df["High"])
        & (df["High"].shift(-lookback) < df["High"])
    ]
    df["swing_low"] = df["Low"][
        (df["Low"].shift(lookback) > df["Low"])
        & (df["Low"].shift(-lookback) > df["Low"])
    ]
    return df


# --- Triangle patterns ---

def detect_ascending_triangle(df: pd.DataFrame, window: int = 80) -> float:
    if df.empty:
        return 0.0
    sub = df.tail(window)
    swings = _find_swings(sub)
    highs = swings["swing_high"].dropna().tail(6)
    lows = swings["swing_low"].dropna().tail(6)
    if len(highs) < 2 or len(lows) < 2:
        return 0.0

    high_range = highs.max() - highs.min()
    high_mean = highs.mean()
    flat_score = (1.0 - (high_range / high_mean)) if high_mean > 0 else 0.0
    rising_score = _line_slope(lows.values) * 50.0 + 0.5
    return _to_score(0.6 * flat_score + 0.4 * rising_score)


def detect_sym_triangle(df: pd.DataFrame, window: int = 80) -> float:
    if df.empty:
        return 0.0
    sub = df.tail(window)
    swings = _find_swings(sub)
    highs = swings["swing_high"].dropna().tail(8)
    lows = swings["swing_low"].dropna().tail(8)
    if len(highs) < 3 or len(lows) < 3:
        return 0.0

    h_slope = _line_slope(highs.values)
    l_slope = _line_slope(lows.values)
    h_arr, l_arr = highs.values, lows.values
    range_start = h_arr[0] - l_arr[0]
    range_end = h_arr[-1] - l_arr[-1]
    if range_start <= 0:
        return 0.0

    compression = max(0.0, 1.0 - (range_end / range_start))
    dir_score = 1.0 if (h_slope < 0 and l_slope > 0) else 0.0
    return _to_score(0.7 * compression + 0.3 * dir_score)


# --- Wedge patterns ---

def _detect_wedge(df: pd.DataFrame, direction: str = "falling", window: int = 80) -> float:
    if df.empty or len(df.tail(window)) < 10:
        return 0.0
    sub = df.tail(window)
    highs, lows, prices = sub["High"].values, sub["Low"].values, sub["Close"].values
    h_slope = _line_slope(highs)
    l_slope = _line_slope(lows)
    p_slope = _line_slope(prices)

    range_start = highs[0] - lows[0]
    range_end = highs[-1] - lows[-1]
    if range_start <= 0:
        return 0.0
    compression = max(0.0, 1.0 - (range_end / range_start))

    if direction == "falling":
        if not (p_slope < 0 and h_slope < 0 and l_slope < 0):
            return 0.0
    else:
        if not (p_slope > 0 and h_slope > 0 and l_slope > 0):
            return 0.0

    parallel_penalty = np.exp(-10 * abs(h_slope - l_slope))
    return _to_score(0.7 * compression + 0.3 * parallel_penalty)


def detect_falling_wedge(df: pd.DataFrame) -> float:
    return _detect_wedge(df, "falling")


def detect_rising_wedge(df: pd.DataFrame) -> float:
    return _detect_wedge(df, "rising")


# --- Flag patterns ---

def detect_flag(df: pd.DataFrame, direction: str = "bullish",
                impulse_window: int = 25, flag_window: int = 10) -> float:
    if df.empty:
        return 0.0
    total = impulse_window + flag_window
    sub = df.tail(total)
    if len(sub) < total:
        return 0.0

    prices = sub["Close"].values
    impulse = prices[:impulse_window]
    flag = prices[impulse_window:]

    if impulse[0] == 0:
        return 0.0
    impulse_ret = (impulse[-1] - impulse[0]) / impulse[0]
    impulse_slope = _line_slope(impulse)
    flag_slope = _line_slope(flag)
    impulse_vol = np.std(impulse)
    flag_vol = max(np.std(flag), 1e-6)
    vol_ratio = flag_vol / max(impulse_vol, 1e-6)

    if direction == "bullish":
        if impulse_ret <= 0.05 or flag_slope > impulse_slope * 0.2:
            return 0.0
    else:
        if impulse_ret >= -0.05 or flag_slope < impulse_slope * 0.2:
            return 0.0

    impulse_strength = min(1.0, abs(impulse_ret) / 0.15)
    vol_score = max(0.0, 1.0 - vol_ratio)
    return _to_score(0.6 * impulse_strength + 0.4 * vol_score)


# --- Double/Triple patterns ---

def detect_double_bottom(df: pd.DataFrame, tolerance: float = 0.02) -> float:
    swings = _find_swings(df)
    lows = swings["swing_low"].dropna().tail(6)
    if len(lows) < 2:
        return 0.0
    last, prev = lows.iloc[-1], lows.iloc[-2]
    return 1.0 if (prev != 0 and abs(last - prev) / abs(prev) <= tolerance) else 0.0


def detect_triple_bottom(df: pd.DataFrame, tolerance: float = 0.02) -> float:
    swings = _find_swings(df)
    lows = swings["swing_low"].dropna().tail(8)
    if len(lows) < 3:
        return 0.0
    last3 = lows.iloc[-3:].values
    ref = last3.mean()
    if ref == 0:
        return 0.0
    return 1.0 if (np.abs(last3 - ref) / abs(ref) <= tolerance).all() else 0.0


def detect_double_top(df: pd.DataFrame, tolerance: float = 0.02) -> float:
    swings = _find_swings(df)
    highs = swings["swing_high"].dropna().tail(6)
    if len(highs) < 2:
        return 0.0
    last, prev = highs.iloc[-1], highs.iloc[-2]
    return 1.0 if (prev != 0 and abs(last - prev) / abs(prev) <= tolerance) else 0.0


def detect_triple_top(df: pd.DataFrame, tolerance: float = 0.02) -> float:
    swings = _find_swings(df)
    highs = swings["swing_high"].dropna().tail(8)
    if len(highs) < 3:
        return 0.0
    last3 = highs.iloc[-3:].values
    ref = last3.mean()
    if ref == 0:
        return 0.0
    return 1.0 if (np.abs(last3 - ref) / abs(ref) <= tolerance).all() else 0.0


# --- Head & Shoulders ---

def detect_head_shoulders(df: pd.DataFrame) -> float:
    swings = _find_swings(df)
    highs = swings["swing_high"].dropna().tail(7)
    if len(highs) < 3:
        return 0.0
    L, H, R = highs.iloc[-3], highs.iloc[-2], highs.iloc[-1]
    if H <= L or H <= R or H == 0:
        return 0.0
    return _to_score(1.0 - (abs(L - R) / abs(H)))


def detect_inverse_head_shoulders(df: pd.DataFrame) -> float:
    swings = _find_swings(df)
    lows = swings["swing_low"].dropna().tail(7)
    if len(lows) < 3:
        return 0.0
    L, H, R = lows.iloc[-3], lows.iloc[-2], lows.iloc[-1]
    if H >= L or H >= R:
        return 0.0
    ref = max(abs(H), 1e-6)
    return _to_score(1.0 - (abs(L - R) / ref))


# --- Master detector ---

def detect_chart_patterns(df: pd.DataFrame) -> dict:
    """Return dict of pattern_name -> score (0-1) for all tracked patterns."""
    if df is None or df.empty:
        return {name: 0.0 for name in PATTERN_FEATURE_COLUMNS}

    return {
        "ascending_triangle": detect_ascending_triangle(df),
        "bullish_flag": detect_flag(df, "bullish"),
        "bullish_wedge": detect_falling_wedge(df),
        "bullish_sym_triangle": detect_sym_triangle(df),
        "descending_triangle": 0.0,  # TODO: implement mirror of ascending
        "bearish_flag": detect_flag(df, "bearish"),
        "bearish_wedge": detect_rising_wedge(df),
        "bearish_sym_triangle": detect_sym_triangle(df),
        "double_bottom": detect_double_bottom(df),
        "triple_bottom": detect_triple_bottom(df),
        "inverse_head_shoulders": detect_inverse_head_shoulders(df),
        "falling_wedge_rev": detect_falling_wedge(df),
        "double_top": detect_double_top(df),
        "triple_top": detect_triple_top(df),
        "head_shoulders": detect_head_shoulders(df),
        "rising_wedge_rev": detect_rising_wedge(df),
    }


def append_pattern_features(df: pd.DataFrame, pattern_scores: dict = None) -> pd.DataFrame:
    """Attach pattern scores as columns across the dataframe."""
    if df is None or df.empty:
        return df
    if pattern_scores is None:
        pattern_scores = detect_chart_patterns(df)

    df = df.copy()
    for name in PATTERN_FEATURE_COLUMNS:
        val = pattern_scores.get(name, 0.0)
        if isinstance(val, (list, np.ndarray)):
            val = float(np.asarray(val, dtype="float64").ravel()[0])
        df[name] = float(val)
    return df
