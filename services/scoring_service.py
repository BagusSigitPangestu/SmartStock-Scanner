"""
SmartStock Scanner — Ensemble Scoring Service
Combines all 3 layers into a single score /100.
Scoring Gate: Only pass stocks with score >= threshold.
"""

import logging

import pandas as pd

import config
from services.kalman_service import score_kalman
from services.indicator_service import compute_indicators, compute_vwap, score_indicators
from services.pattern_service import detect_patterns
from services.volume_service import analyze_volume
from services.adimology_service import calculate_targets

logger = logging.getLogger(__name__)


def score_stock(
    ticker: str,
    df: pd.DataFrame,
    df_intraday: pd.DataFrame | None = None,
    trade_type: str = config.TRADE_TYPE_SWING,
) -> dict | None:
    """
    Run the full ensemble scoring pipeline on a single stock.

    Returns a result dict with total score, layer breakdown, and signal details.
    Returns None if data is insufficient.
    """
    if df.empty or len(df) < 20:
        logger.warning(f"[{ticker}] Skipped — insufficient data ({len(df)} bars)")
        return None

    # --- Layer A: Kalman Filter (0-30) ---
    kalman_result = score_kalman(df)

    # --- Layer B: Technical Indicators (0-30) ---
    df = compute_indicators(df)
    vwap = compute_vwap(df_intraday) if df_intraday is not None else None
    indicator_result = score_indicators(df, vwap=vwap)

    # --- Layer C: Volume & Pattern (0-40) ---
    patterns = detect_patterns(df)
    volume_data = analyze_volume(df)

    vol_score = 0
    vol_details_parts = []

    # Volume spike (max +10)
    spike = volume_data.get("spike_ratio", 0)
    if spike >= config.VOLUME_SPIKE_MULTIPLIER:
        vol_score += 10
        vol_details_parts.append(f"Vol {spike:.1f}x Avg (Accumulating)")
    elif spike >= 1.0:
        vol_score += 4
        vol_details_parts.append(f"Vol {spike:.1f}x Avg")
    else:
        vol_details_parts.append(f"Vol {spike:.1f}x Avg (Low)")

    # VBP support (max +10)
    if volume_data.get("vbp_support"):
        vol_score += 10
        vol_details_parts.append(f"VBP Support @ {volume_data.get('vbp_level')}")

    # Candlestick patterns (max +10)
    if patterns:
        vol_score += min(len(patterns) * 5, 10)
        vol_details_parts.append(f"Pattern: {', '.join(patterns)}")

    # VWAP bonus in volume layer (max +10)
    if vwap and not df.empty:
        price = df["Close"].iloc[-1]
        if price > vwap:
            vol_score += 10
            vol_details_parts.append("Price > VWAP ✓")

    vol_score = min(vol_score, config.VOLUME_PATTERN_MAX_SCORE)
    volume_result = {
        "score": vol_score,
        "details": " | ".join(vol_details_parts),
        "patterns": patterns,
        "volume_spike": spike,
    }

    # --- Total Score ---
    total_score = kalman_result["score"] + indicator_result["score"] + volume_result["score"]
    total_score = min(total_score, 100)

    # Signal strength label
    if total_score >= config.SCORE_STRONG_SIGNAL:
        strength = "Strong Signal 🔥"
    elif total_score >= config.SCORE_BUY_THRESHOLD:
        strength = "Moderate Signal"
    else:
        strength = "Weak"

    # Entry / SL / TP from latest price data
    current_price = float(df["Close"].iloc[-1])

    # Calculate Adimology Targets if we have VWAP and enough data
    adimology = None
    if vwap and len(df) >= 2:
        prev_close = float(df["Close"].iloc[-2])
        current_vol = float(df["Volume"].iloc[-1])
        adimology = calculate_targets(vwap, current_vol, prev_close, current_price)

    return {
        "ticker": ticker,
        "trade_type": trade_type,
        "total_score": total_score,
        "strength": strength,
        "current_price": current_price,
        "kalman": kalman_result,
        "indicators": indicator_result,
        "volume": volume_result,
        "vwap": vwap,
        "adimology": adimology,
    }


def _get_threshold(trade_type: str) -> int:
    """Get the scoring threshold for a specific trade type."""
    thresholds = {
        config.TRADE_TYPE_DAY: config.THRESHOLD_DAY_TRADING,
        config.TRADE_TYPE_BSJP: config.THRESHOLD_BSJP,
        config.TRADE_TYPE_SWING: config.THRESHOLD_SWING,
    }
    return thresholds.get(trade_type, config.SCORE_BUY_THRESHOLD)


def run_screening(
    bulk_data: dict[str, pd.DataFrame],
    intraday_data: dict[str, pd.DataFrame] | None = None,
    trade_type: str = config.TRADE_TYPE_SWING,
    min_score: int | None = None,
) -> list[dict]:
    """
    Run ensemble scoring on all stocks and return those passing the scoring gate.
    Threshold is auto-selected per trade type if min_score is not specified.
    Results are sorted by total_score descending.
    """
    if min_score is None:
        min_score = _get_threshold(trade_type)

    results = []

    for ticker, df in bulk_data.items():
        df_intra = intraday_data.get(ticker) if intraday_data else None
        result = score_stock(ticker, df, df_intra, trade_type)

        if result and result["total_score"] >= min_score:
            results.append(result)

    results.sort(key=lambda x: x["total_score"], reverse=True)
    logger.info(f"Screening complete: {len(results)} stocks passed (threshold={min_score})")
    return results
