"""
SmartStock Scanner — Kalman Filter Service (Layer A: Signal Processing)
Estimates the "true" hidden price using a 1D Kalman Filter.
Score: 0-30
"""

import logging

import numpy as np
import pandas as pd

import config

logger = logging.getLogger(__name__)


def apply_kalman_filter(prices: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Apply a simple 1D Kalman Filter to price series.

    Returns:
        estimates: Kalman-filtered price estimates
        slopes: First-derivative (slope) of the Kalman estimate
    """
    n = len(prices)
    if n < 5:
        return np.full(n, np.nan), np.full(n, np.nan)

    dt = 1.0
    F = np.array([[1, dt], [0, 1]])
    H = np.array([[1, 0]])

    q = 0.01
    Q = q * np.array([[dt**3 / 3, dt**2 / 2],
                       [dt**2 / 2, dt]])
    R = np.array([[1.0]])

    x = np.array([prices[0], 0.0])
    P = np.eye(2) * 100.0

    estimates = np.zeros(n)
    slopes = np.zeros(n)

    for i in range(n):
        x_pred = F @ x
        P_pred = F @ P @ F.T + Q

        z = prices[i]
        y_residual = z - H @ x_pred
        S = H @ P_pred @ H.T + R
        K = P_pred @ H.T @ np.linalg.inv(S)

        x = x_pred + K.flatten() * y_residual.item()
        P = (np.eye(2) - K @ H) @ P_pred

        estimates[i] = x[0]
        slopes[i] = x[1]

    return estimates, slopes


def score_kalman(df: pd.DataFrame) -> dict:
    """
    Calculate Kalman Filter score for a stock.

    Scoring Logic (max 30):
        - Price crosses Kalman from below (bullish crossover):   +10
        - Positive slope (upward trend):                         +8
        - Price above or near Kalman estimate:                   +6
        - Slope improving (accelerating upward):                 +6

    Returns dict with score and details.
    """
    if df.empty or len(df) < 10:
        return {"score": 0, "details": "Insufficient data", "kalman_val": None, "slope": None}

    prices = df["Close"].values
    estimates, slopes = apply_kalman_filter(prices)

    current_price = prices[-1]
    kalman_val = estimates[-1]
    current_slope = slopes[-1]

    prev_price = prices[-2]
    prev_kalman = estimates[-2]
    prev_slope = slopes[-2]

    score = 0
    details = []

    # 1. Bullish crossover: price crossed Kalman from below (+10)
    crossover = (prev_price < prev_kalman) and (current_price > kalman_val)
    if crossover:
        score += 10
        details.append("Crossover ↑ (Bullish)")

    # 2. Positive slope / upward trend (+8)
    if current_slope > 0:
        score += 8
        details.append(f"Trend Up (slope={current_slope:.2f})")
    elif current_slope > -abs(kalman_val * 0.001):
        # Slope is nearly flat — transitioning
        score += 3
        details.append(f"Trend Flat (slope={current_slope:.2f})")
    else:
        details.append(f"Trend Down (slope={current_slope:.2f})")

    # 3. Price position relative to Kalman (+6)
    distance_pct = (current_price - kalman_val) / kalman_val * 100 if kalman_val != 0 else 0

    if current_price > kalman_val:
        if distance_pct < 3:
            score += 6
            details.append(f"Price > Kalman (+{distance_pct:.1f}%)")
        else:
            score += 3  # Extended above
            details.append(f"Price >> Kalman (+{distance_pct:.1f}%)")
    elif distance_pct > -1.5:
        # Price is close below Kalman — potential bounce
        score += 4
        details.append(f"Near Kalman (-{abs(distance_pct):.1f}%)")
    else:
        details.append(f"Price < Kalman (-{abs(distance_pct):.1f}%)")

    # 4. Slope improving (accelerating up) (+6)
    if current_slope > prev_slope:
        score += 6
        details.append("Slope Accelerating ↑")
    elif current_slope > prev_slope * 0.9:
        score += 2
        details.append("Slope Stable")

    score = min(score, config.KALMAN_MAX_SCORE)

    return {
        "score": score,
        "details": " | ".join(details),
        "kalman_val": round(kalman_val, 2),
        "slope": round(current_slope, 4),
    }
