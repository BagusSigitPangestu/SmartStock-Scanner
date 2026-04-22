"""
SmartStock Scanner — Candlestick Pattern Detection
Detects: Hammer, Bullish Engulfing, Gap Up (BSJP)
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def detect_patterns(df: pd.DataFrame) -> list[str]:
    """
    Detect bullish candlestick patterns on the last few bars.
    Returns list of pattern names found.
    """
    if df.empty or len(df) < 3:
        return []

    patterns = []

    # Check last 3 candles for patterns
    for i in range(-1, max(-4, -len(df)), -1):
        candle = df.iloc[i]
        prev = df.iloc[i - 1] if abs(i - 1) <= len(df) else None

        # Hammer detection
        if _is_hammer(candle):
            patterns.append("Hammer")

        # Bullish Engulfing
        if prev is not None and _is_bullish_engulfing(prev, candle):
            patterns.append("Bullish Engulfing")

    # Gap Up (between last 2 days)
    if len(df) >= 2:
        if _is_gap_up(df.iloc[-2], df.iloc[-1]):
            patterns.append("Gap Up")

    # Deduplicate
    return list(set(patterns))


def _is_hammer(candle: pd.Series) -> bool:
    """
    Hammer: small body at top, long lower shadow (>= 2x body), tiny upper shadow.
    Indicates potential reversal after downtrend.
    """
    o, h, l, c = candle["Open"], candle["High"], candle["Low"], candle["Close"]

    body = abs(c - o)
    total_range = h - l

    if total_range == 0:
        return False

    lower_shadow = min(o, c) - l
    upper_shadow = h - max(o, c)

    # Body is small relative to total range
    body_ratio = body / total_range
    # Lower shadow is at least 2x the body
    has_long_lower = lower_shadow >= 2 * body if body > 0 else lower_shadow > total_range * 0.6
    # Upper shadow is small
    has_small_upper = upper_shadow < body * 0.5 if body > 0 else upper_shadow < total_range * 0.1

    return body_ratio < 0.35 and has_long_lower and has_small_upper


def _is_bullish_engulfing(prev: pd.Series, curr: pd.Series) -> bool:
    """
    Bullish Engulfing: previous candle is bearish, current candle is bullish
    and completely engulfs the previous body.
    """
    prev_bearish = prev["Close"] < prev["Open"]
    curr_bullish = curr["Close"] > curr["Open"]

    if not (prev_bearish and curr_bullish):
        return False

    # Current body engulfs previous body
    curr_engulfs = curr["Open"] <= prev["Close"] and curr["Close"] >= prev["Open"]

    return curr_engulfs


def _is_gap_up(prev: pd.Series, curr: pd.Series) -> bool:
    """
    Gap Up: current candle opens above previous candle's high.
    Strong bullish signal, especially for BSJP strategy.
    """
    gap_threshold = 0.005  # at least 0.5% gap
    gap_pct = (curr["Open"] - prev["High"]) / prev["High"]
    return gap_pct > gap_threshold
