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


def check_bsjp_criteria(df: pd.DataFrame) -> tuple[bool, str]:
    """Filter logic for Day Trading (BSJP Momentum)"""
    if df.empty or len(df) < 20:
        return False, ""
    
    current = df.iloc[-1]
    
    # 1. Trend: Close > EMA5 AND EMA5 > EMA20 (MA20 in current code)
    if pd.isna(current.get("EMA5")) or pd.isna(current.get("MA20")):
        return False, ""
    if not (current["Close"] > current["EMA5"] and current["EMA5"] > current["MA20"]):
        return False, ""
        
    # 2. Strength: 55 <= RSI <= 72
    rsi = current.get("RSI")
    if pd.isna(rsi) or not (55 <= rsi <= 72):
        return False, ""
        
    # 3. Volume: Vol_Ratio >= 1.5
    vol_ratio = current.get("Vol_Ratio")
    if pd.isna(vol_ratio) or vol_ratio < 1.5:
        return False, ""
        
    # 4. Price Action: RC >= 0.8
    rc = current.get("RC")
    if pd.isna(rc) or rc < 0.8:
        return False, ""
        
    return True, f"BSJP Momentum (RC: {rc:.2f}, Vol: {vol_ratio:.1f}x)"

def check_swing_criteria(df: pd.DataFrame) -> tuple[bool, str]:
    """Filter logic for Swing Trading (Trend Following)"""
    if df.empty or len(df) < 50:
        return False, ""
        
    current = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Setup A: Golden Cross (Trend Reversal)
    # SMA20 memotong ke atas SMA50 dalam 3 hari terakhir AND Close > SMA20
    setup_a = False
    if pd.notna(current.get("MA20")) and pd.notna(current.get("SMA50")):
        if current["Close"] > current["MA20"]:
            cross_found = False
            for i in range(1, 4):
                if len(df) > i:
                    curr_day = df.iloc[-i]
                    prev_day = df.iloc[-(i+1)]
                    if prev_day["MA20"] <= prev_day["SMA50"] and curr_day["MA20"] > curr_day["SMA50"]:
                        cross_found = True
                        break
            setup_a = cross_found
            
    # Setup B: Momentum Shift (MACD)
    # MACD_Line > Signal_Line AND Hist_today > Hist_yesterday AND Stoch %K < 40
    setup_b = False
    if (pd.notna(current.get("MACD_Line")) and pd.notna(current.get("MACD_Signal")) and 
        pd.notna(current.get("MACD_Hist")) and pd.notna(prev.get("MACD_Hist")) and 
        pd.notna(current.get("Stoch_K"))):
        if (current["MACD_Line"] > current["MACD_Signal"] and 
            current["MACD_Hist"] > prev["MACD_Hist"] and 
            current["Stoch_K"] < 40):
            setup_b = True
            
    if setup_a:
        return True, "Swing: Golden Cross (SMA20x50)"
    elif setup_b:
        return True, "Swing: MACD Momentum Shift"
        
    return False, ""

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
    
    # --- PRD2 Hard Filter ---
    setup_name = "Ensemble Basic"
    if trade_type in [config.TRADE_TYPE_BSJP, config.TRADE_TYPE_DAY]:
        passed, setup_name = check_bsjp_criteria(df)
        if not passed:
            return None
    elif trade_type == config.TRADE_TYPE_SWING:
        passed, setup_name = check_swing_criteria(df)
        if not passed:
            return None

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
        "setup_name": setup_name,
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
