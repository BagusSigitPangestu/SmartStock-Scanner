"""
SmartStock Scanner — Telegram Message Formatter
Builds HTML-formatted alert messages matching the PRD template.
"""

import config


def format_signal_message(result: dict) -> str:
    """
    Format a single stock signal into an HTML Telegram message.
    Follows the PRD notification template.
    """
    ticker = result["ticker"]
    trade_type = result.get("trade_type", "Swing Trading")
    score = result["total_score"]
    strength = result.get("strength", "")

    # Kalman details
    k = result.get("kalman", {})
    kalman_detail = k.get("details", "N/A")
    kalman_slope = k.get("slope", 0)
    kalman_trend = "Trend Up (Positive Slope)" if kalman_slope and kalman_slope > 0 else "Trend Down"

    # Indicator details
    ind = result.get("indicators", {})
    ma_status = ind.get("ma_status", "N/A")
    rsi = ind.get("rsi")
    rsi_str = f"RSI: {rsi:.0f}" if rsi else "RSI: N/A"

    # Volume details
    vol = result.get("volume", {})
    vol_spike = vol.get("volume_spike", 0)
    patterns = vol.get("patterns", [])
    vol_label = f"{vol_spike:.1f}x Average"
    if vol_spike >= config.VOLUME_SPIKE_MULTIPLIER:
        vol_label += " (Accumulating)"

    # Price levels
    entry = result.get("entry", 0)
    tp = result.get("tp", 0)
    sl = result.get("sl", 0)
    risk_pct = result.get("risk_pct", 0)
    risk_warn = result.get("risk_warning", "")

    # Score bar visual
    filled = int(score / 10)
    bar = "█" * filled + "░" * (10 - filled)

    msg = (
        f"📊 <b>SHORT-TERM ALERT: {ticker}</b>\n"
        f"\n"
        f"🏷️ Type: <b>{trade_type}</b>\n"
        f"🏆 Score: <b>{score}/100</b> ({strength})\n"
        f"[{bar}]\n"
        f"\n"
        f"💹 <b>Strategi:</b>\n"
        f"    ├ Kalman: {kalman_trend}\n"
        f"    ├ MA: {ma_status}\n"
        f"    ├ {rsi_str}\n"
        f"    └ Vol: {vol_label}\n"
    )

    if patterns:
        msg += f"🕯️ Pattern: {', '.join(patterns)}\n"

    adimology = result.get("adimology")
    adimology_str = ""
    if adimology:
        r1 = adimology.get("target_r1", 0)
        rmax = adimology.get("target_max", 0)
        adimology_str = (
            f"🎯 Adimology R1: <b>Rp{r1:,.0f}</b>\n"
            f"🎯 Adimology Max: <b>Rp{rmax:,.0f}</b>\n"
        )

    msg += (
        f"\n"
        f"📥 Entry: <b>Rp{entry:,.0f}</b>\n"
        f"🎯 TP (Standard): <b>Rp{tp:,.0f}</b>\n"
        f"{adimology_str}"
        f"🛡️ SL: <b>Rp{sl:,.0f}</b> (Risk: {risk_pct:.1f}%)\n"
    )

    if risk_warn:
        msg += f"\n{risk_warn}\n"

    return msg


def format_scan_summary(results: list[dict], trade_type: str) -> str:
    """
    Format a summary header for a batch scan.
    """
    total = len(results)
    if total == 0:
        return (
            f"📡 <b>Scan Complete — {trade_type}</b>\n\n"
            f"Tidak ada saham yang lolos Scoring Gate "
            f"(threshold: {config.SCORE_BUY_THRESHOLD}/100).\n"
            f"Pasar mungkin sedang sideways. Tunggu momentum berikutnya."
        )

    strong = sum(1 for r in results if r["total_score"] >= config.SCORE_STRONG_SIGNAL)

    header = (
        f"📡 <b>SCAN COMPLETE — {trade_type}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ {total} saham lolos screening\n"
        f"🔥 {strong} Strong Signal\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    return header


def format_no_results_message() -> str:
    """Message when no stocks pass the screening."""
    return (
        "📡 <b>Scan Complete</b>\n\n"
        "🔍 Tidak ada sinyal BUY saat ini.\n"
        "Semua saham belum memenuhi kriteria Ensemble Scoring Gate.\n\n"
        "💡 <i>Tip: Pasar mungkin sedang sideways. "
        "Tunggu momentum yang lebih jelas.</i>"
    )
