"""
SmartStock Scanner — Excel Export Service
Export signal history to .xlsx for weekly backtesting.
"""

import logging
from datetime import datetime, timezone

import pandas as pd

from database.db import get_session
from database.models import Signal, Analysis

logger = logging.getLogger(__name__)


def export_signals_to_excel(filepath: str | None = None) -> str:
    """
    Export all signals from the database to an Excel file.
    Returns the file path of the generated Excel.
    """
    if filepath is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filepath = f"exports/smartstock_signals_{ts}.xlsx"

    session = get_session()
    try:
        signals = session.query(Signal).order_by(Signal.timestamp.desc()).all()

        if not signals:
            logger.warning("No signals to export.")
            return ""

        data = []
        for s in signals:
            data.append({
                "Ticker": s.ticker,
                "Timestamp": s.timestamp,
                "Type": s.trade_type,
                "Score": s.score,
                "Entry": s.entry,
                "TP": s.tp,
                "SL": s.sl,
                "Risk %": s.risk_pct,
                "Status": s.win_loss_status,
            })

        df = pd.DataFrame(data)

        # Ensure exports directory exists
        import os
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else "exports", exist_ok=True)

        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Signals", index=False)

            # Summary sheet
            summary_data = {
                "Metric": [
                    "Total Signals",
                    "Open",
                    "Win",
                    "Loss",
                    "Win Rate (%)",
                    "Avg Score",
                ],
                "Value": [
                    len(df),
                    len(df[df["Status"] == "OPEN"]),
                    len(df[df["Status"] == "WIN"]),
                    len(df[df["Status"] == "LOSS"]),
                    _calc_win_rate(df),
                    round(df["Score"].mean(), 1) if len(df) > 0 else 0,
                ],
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name="Summary", index=False)

        logger.info(f"Exported {len(df)} signals to {filepath}")
        return filepath

    except Exception as e:
        logger.error(f"Export error: {e}")
        return ""
    finally:
        session.close()


def _calc_win_rate(df: pd.DataFrame) -> float:
    """Calculate win rate from closed trades."""
    closed = df[df["Status"].isin(["WIN", "LOSS"])]
    if len(closed) == 0:
        return 0.0
    wins = len(closed[closed["Status"] == "WIN"])
    return round(wins / len(closed) * 100, 1)
