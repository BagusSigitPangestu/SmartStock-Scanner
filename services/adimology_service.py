"""
SmartStock Scanner — Adimology Target Service
Adapted from Adi Sucipto's Target Algorithm for Technical Data.
"""

import logging

logger = logging.getLogger(__name__)

def get_fraksi(harga: float) -> int:
    """Calculate Fraksi based on IDX stock price rules."""
    if harga < 200:
        return 1
    if harga < 500:
        return 2
    if harga < 2000:
        return 5
    if harga < 5000:
        return 10
    return 25

def get_ara_arb(prev_close: float) -> tuple[float, float]:
    """Calculate Auto Reject Atas (ARA) and Auto Reject Bawah (ARB) based on IDX rules."""
    if prev_close < 200:
        pct = 0.35
    elif prev_close < 5000:
        pct = 0.25
    else:
        pct = 0.20
    
    fraksi = get_fraksi(prev_close)
    if fraksi == 0:
        return prev_close, prev_close

    ara_raw = prev_close * (1 + pct)
    arb_raw = prev_close * (1 - pct)
    
    # Round to nearest fraksi
    ara = round(ara_raw / fraksi) * fraksi
    arb = round(arb_raw / fraksi) * fraksi
    
    # Minimum price in IDX regular board is usually 50
    return ara, max(50, arb)

def calculate_targets(vwap: float, volume: float, prev_close: float, current_price: float) -> dict:
    """
    Calculate target prices based on Adimology.
    Adapting Broker data (Bandarmology) to Technical proxy (VWAP and Volume).
    """
    try:
        fraksi = get_fraksi(current_price)
        ara, arb = get_ara_arb(prev_close)
        
        # Total Papan = (ARA - ARB) / Fraksi
        total_papan = (ara - arb) / fraksi if fraksi > 0 else 1
        if total_papan <= 0:
            total_papan = 1
        
        # Proxy for rataRataBidOfer: Average daily volume / total_papan
        rata_rata_bid_ofer = volume / total_papan if total_papan > 0 else 1
        
        # a = Rata rata bandar (VWAP as proxy) × 5%
        a = vwap * 0.05
        
        # Proxy for barangBandar: Assuming ~30% of daily volume is accumulated
        barang_bandar = volume * 0.30
        
        # p = Barang Bandar / Rata rata Bid Ofer
        p = barang_bandar / rata_rata_bid_ofer if rata_rata_bid_ofer > 0 else 0
        
        # Target Realistis = Rata rata bandar + a + (p/2 × Fraksi)
        target_r1 = vwap + a + ((p / 2) * fraksi)
        
        # Target Max = Rata rata bandar + a + (p × Fraksi)
        target_max = vwap + a + (p * fraksi)
        
        # Rounding & Capping at ARA
        target_r1 = min(round(target_r1), ara)
        target_max = min(round(target_max), ara)
        
        # Ensure targets are not below current price if possible (just a sanity check)
        target_r1 = max(target_r1, current_price)
        target_max = max(target_max, target_r1)
        
        return {
            "fraksi": fraksi,
            "ara": ara,
            "arb": arb,
            "target_r1": target_r1,
            "target_max": target_max
        }
    except Exception as e:
        logger.error(f"Error calculating adimology targets: {e}")
        return None
