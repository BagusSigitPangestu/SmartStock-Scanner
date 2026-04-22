"""
SmartStock Scanner — Technical Indicator Service (Layer B: Psychological Layer)
MA20, MA200, RSI, Bollinger Bands, VWAP
Score: 0-30
"""

import logging

import numpy as np
import pandas as pd

import config

logger = logging.getLogger(__name__)


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all technical indicators on the DataFrame.
    Modifies df in-place and returns it.
    """
    if df.empty or len(df) < config.MA_SHORT_PERIOD:
        return df

    # Moving Averages
    df["MA20"] = df["Close"].rolling(window=config.MA_SHORT_PERIOD).mean()
    if len(df) >= config.MA_LONG_PERIOD:
        df["MA200"] = df["Close"].rolling(window=config.MA_LONG_PERIOD).mean()
    else:
        df["MA200"] = np.nan

    # RSI
    df["RSI"] = _compute_rsi(df["Close"], period=config.RSI_PERIOD)

    # Bollinger Bands
    df["BB_Middle"] = df["Close"].rolling(window=config.BB_PERIOD).mean()
    bb_std = df["Close"].rolling(window=config.BB_PERIOD).std()
    df["BB_Upper"] = df["BB_Middle"] + config.BB_STD * bb_std
    df["BB_Lower"] = df["BB_Middle"] - config.BB_STD * bb_std

    # --- New Indicators for BSJP & Swing (PRD2) ---
    # EMA 5
    df["EMA5"] = df["Close"].ewm(span=5, adjust=False).mean()
    
    # SMA 50
    if len(df) >= 50:
        df["SMA50"] = df["Close"].rolling(window=50).mean()
    else:
        df["SMA50"] = np.nan

    # Volume Ratio
    df["Vol_SMA20"] = df["Volume"].rolling(window=20).mean()
    df["Vol_Ratio"] = df["Volume"] / df["Vol_SMA20"]

    # Relative Close (RC)
    high_low_diff = df["High"] - df["Low"]
    df["RC"] = np.where(high_low_diff > 0, (df["Close"] - df["Low"]) / high_low_diff, 0)

    # MACD (12, 26, 9)
    exp12 = df["Close"].ewm(span=12, adjust=False).mean()
    exp26 = df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD_Line"] = exp12 - exp26
    df["MACD_Signal"] = df["MACD_Line"].ewm(span=9, adjust=False).mean()
    df["MACD_Hist"] = df["MACD_Line"] - df["MACD_Signal"]

    # Stochastic Oscillator (14, 3, 3)
    # Standard %K is (Close - Low14) / (High14 - Low14) * 100
    # PRD specifies (14, 3, 3) which means %K is 3-period SMA of raw %K, and %D is 3-period SMA of %K.
    # We'll just calculate standard %K and smooth it.
    if len(df) >= 14:
        low_14 = df["Low"].rolling(window=14).min()
        high_14 = df["High"].rolling(window=14).max()
        raw_k = 100 * (df["Close"] - low_14) / (high_14 - low_14)
        df["Stoch_K"] = raw_k.rolling(window=3).mean()  # 3-period smooth for %K
        df["Stoch_D"] = df["Stoch_K"].rolling(window=3).mean() # 3-period smooth for %D
    else:
        df["Stoch_K"] = np.nan
        df["Stoch_D"] = np.nan

    return df


def compute_vwap(df_intraday: pd.DataFrame) -> float | None:
    """
    Compute VWAP from intraday data.
    VWAP = Cumulative(Typical Price * Volume) / Cumulative(Volume)
    """
    if df_intraday.empty or "Volume" not in df_intraday.columns:
        return None

    try:
        tp = (df_intraday["High"] + df_intraday["Low"] + df_intraday["Close"]) / 3
        cum_tp_vol = (tp * df_intraday["Volume"]).cumsum()
        cum_vol = df_intraday["Volume"].cumsum()

        vwap_series = cum_tp_vol / cum_vol
        vwap = vwap_series.iloc[-1]

        return round(float(vwap), 2) if pd.notna(vwap) and vwap > 0 else None
    except Exception:
        return None


def _compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI using exponential weighted moving average."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def score_indicators(df: pd.DataFrame, vwap: float | None = None) -> dict:
    """
    Calculate indicator score for a stock.

    Scoring Logic (max 30):
        - Price > MA20 (short-term uptrend):         +7
        - Price near MA20 (approaching support):     +3
        - MA20 > MA200 (golden cross zone):          +4
        - RSI oversold (< 30, bounce potential):     +8
        - RSI recovering (30-50):                    +5
        - RSI neutral-bullish (50-65):               +3
        - Price near lower Bollinger Band:           +5
        - Price in lower half of BB:                 +2
        - Price > VWAP (buyers in profit):           +3

    Returns dict with score and details.
    """
    if df.empty or len(df) < config.MA_SHORT_PERIOD:
        return {"score": 0, "details": "Insufficient data", "rsi": None, "ma_status": "N/A"}

    current = df.iloc[-1]
    price = current["Close"]
    score = 0
    details = []

    # 1. Price vs MA20 (+7 above, +3 near)
    ma20 = current.get("MA20")
    if pd.notna(ma20) and ma20 > 0:
        ma20_dist = (price - ma20) / ma20 * 100
        if price > ma20:
            score += 7
            details.append("Price > MA20 ✓")
        elif ma20_dist > -2.0:
            # Price within 2% below MA20 — near support
            score += 3
            details.append(f"Near MA20 (-{abs(ma20_dist):.1f}%)")
        else:
            details.append("Price < MA20 ✗")

    # 2. MA20 > MA200 — Golden Cross zone (+4)
    ma200 = current.get("MA200")
    ma_status = "N/A"
    if pd.notna(ma20) and pd.notna(ma200):
        if ma20 > ma200:
            score += 4
            ma_status = "Golden Cross"
            details.append("MA20 > MA200 (Golden)")
        else:
            ma_status = "Death Cross"
            details.append("MA20 < MA200 (Death)")
    elif pd.notna(ma20):
        ma_status = "MA20 Only"

    # 3. RSI scoring (more granular)
    rsi = current.get("RSI")
    if pd.notna(rsi):
        rsi = float(rsi)
        if rsi < config.RSI_OVERSOLD:
            score += 8
            details.append(f"RSI {rsi:.0f} (Oversold 🔥)")
        elif rsi < 45:
            score += 5
            details.append(f"RSI {rsi:.0f} (Recovering)")
        elif rsi < 65:
            score += 3
            details.append(f"RSI {rsi:.0f} (Healthy)")
        elif rsi > config.RSI_OVERBOUGHT:
            details.append(f"RSI {rsi:.0f} (Overbought ⚠)")
        else:
            score += 1
            details.append(f"RSI {rsi:.0f}")

    # 4. Bollinger Bands position
    bb_lower = current.get("BB_Lower")
    bb_upper = current.get("BB_Upper")
    if pd.notna(bb_lower) and pd.notna(bb_upper):
        bb_range = bb_upper - bb_lower
        if bb_range > 0:
            bb_position = (price - bb_lower) / bb_range
            if bb_position < 0.15:
                score += 5
                details.append(f"Near BB Lower ({bb_position:.0%})")
            elif bb_position < 0.4:
                score += 3
                details.append(f"Below BB Mid ({bb_position:.0%})")
            elif bb_position < 0.6:
                score += 1
                details.append(f"BB Mid ({bb_position:.0%})")
            else:
                details.append(f"BB Upper ({bb_position:.0%})")

    # 5. VWAP (+3)
    if vwap is not None and vwap > 0:
        if price > vwap:
            score += 3
            details.append("Price > VWAP ✓")
        else:
            details.append("Price < VWAP ✗")

    score = min(score, config.INDICATOR_MAX_SCORE)

    return {
        "score": score,
        "details": " | ".join(details),
        "rsi": round(float(rsi), 1) if pd.notna(rsi) else None,
        "ma_status": ma_status,
    }

