"""
SmartStock Scanner — Risk Manager
Implements the 2% Rule Guardrail for position sizing and SL/TP calculation.
"""

import logging

import pandas as pd
import numpy as np

import config

logger = logging.getLogger(__name__)


def calculate_stop_loss(df: pd.DataFrame) -> float | None:
    """
    Calculate Stop Loss using recent swing low or ATR-based method.
    Uses the lowest low of the last 5 bars as SL level.
    """
    if df.empty or len(df) < 5:
        return None

    # Support (S): Nilai terendah (Low) dari 5 hari terakhir.
    recent_low = df["Low"].iloc[-5:].min()
    return float(recent_low)

def calculate_resistance(df: pd.DataFrame) -> float | None:
    """
    Calculate Resistance using the highest high of the last 20 bars.
    """
    if df.empty or len(df) < 20:
        return None
        
    recent_high = df["High"].iloc[-20:].max()
    return float(recent_high)


def calculate_take_profit(entry: float, sl: float, ratio: float = config.DEFAULT_TP_RATIO) -> float:
    """
    Calculate Take Profit based on Risk:Reward ratio.
    Default ratio is 1:2 (risk 1, reward 2).
    """
    risk = entry - sl
    tp = entry + (risk * ratio)
    return round(tp, 2)


def calculate_risk_percent(entry: float, sl: float) -> float:
    """
    Calculate risk as percentage of entry price.
    Risk% = (Entry - SL) / Entry * 100
    """
    if entry <= 0:
        return 999.0
    return round((entry - sl) / entry * 100, 2)


def apply_risk_check(result: dict, df: pd.DataFrame) -> dict:
    """
    Apply the 2% Rule Guardrail to a scoring result.
    Adds entry, sl, tp, risk_pct, and risk_warning to the result dict.
    Calculates Support, Resistance and RRR.
    """
    entry = result["current_price"]
    sl = calculate_stop_loss(df)

    if sl is None or sl >= entry:
        # Fallback: use 2% below entry as SL
        sl = round(entry * 0.98, 2)

    resistance = calculate_resistance(df)
    if resistance is not None and resistance > entry:
        tp = float(resistance)
    else:
        tp = calculate_take_profit(entry, sl)

    risk_pct = calculate_risk_percent(entry, sl)

    # RRR Calculation based on PRD2
    rrr = 0.0
    if (entry - sl) > 0:
        rrr = (tp - entry) / (entry - sl)

    risk_warning = None
    if risk_pct > config.MAX_RISK_PERCENT:
        risk_warning = f"⚠️ High Risk ({risk_pct}%)! Kurangi jumlah lot."
    if rrr < 2.0:
        if risk_warning:
            risk_warning += f"\n⚠️ Low RRR ({rrr:.1f}). Target minimal 2.0!"
        else:
            risk_warning = f"⚠️ Low RRR ({rrr:.1f}). Target minimal 2.0!"

    result["entry"] = round(entry, 2)
    result["sl"] = round(sl, 2)
    result["tp"] = round(tp, 2)
    result["risk_pct"] = risk_pct
    result["rrr"] = round(rrr, 2)
    result["risk_warning"] = risk_warning

    return result
