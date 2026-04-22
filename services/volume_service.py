"""
SmartStock Scanner — Volume Analysis Service
VBP (Volume by Price) and volume spike detection.
Part of Layer C: Confirmation Layer (max score contribution: see scoring_service)
"""

import logging

import numpy as np
import pandas as pd

import config

logger = logging.getLogger(__name__)


def analyze_volume(df: pd.DataFrame) -> dict:
    """
    Analyze volume characteristics:
    1. Volume spike (current vs 20-day average)
    2. VBP (Volume by Price) — identify high-volume support zones
    """
    if df.empty or len(df) < 5:
        return {"spike_ratio": 0, "vbp_support": False, "vbp_level": None}

    current_volume = df["Volume"].iloc[-1]
    avg_volume = df["Volume"].rolling(window=20).mean().iloc[-1]
    spike_ratio = current_volume / avg_volume if avg_volume > 0 else 0

    vbp_support, vbp_level = _compute_vbp(df)

    return {
        "spike_ratio": round(spike_ratio, 2),
        "vbp_support": vbp_support,
        "vbp_level": round(vbp_level, 2) if vbp_level else None,
    }


def _compute_vbp(df: pd.DataFrame) -> tuple[bool, float | None]:
    """
    Volume by Price: bin prices and find Point of Control (highest volume zone).
    Returns (is_near_poc, poc_price).
    """
    try:
        price_min, price_max = df["Low"].min(), df["High"].max()
        if price_max <= price_min:
            return False, None

        bins = np.linspace(price_min, price_max, config.VBP_BINS + 1)
        tp = (df["High"] + df["Low"] + df["Close"]) / 3
        bin_idx = np.clip(np.digitize(tp, bins) - 1, 0, config.VBP_BINS - 1)

        bin_volumes = np.zeros(config.VBP_BINS)
        for i, v in zip(bin_idx, df["Volume"].values):
            bin_volumes[i] += v

        poc_bin = int(np.argmax(bin_volumes))
        poc_price = (bins[poc_bin] + bins[poc_bin + 1]) / 2

        cur_bin = int(np.clip(np.digitize([df["Close"].iloc[-1]], bins)[0] - 1, 0, config.VBP_BINS - 1))
        near_poc = abs(cur_bin - poc_bin) <= 2

        return near_poc, float(poc_price)
    except Exception as e:
        logger.error(f"VBP error: {e}")
        return False, None
