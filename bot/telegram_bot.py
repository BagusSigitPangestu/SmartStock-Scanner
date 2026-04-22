"""
SmartStock Scanner — Telegram Bot Handlers
Commands: /start, /scan, /scan_bsjp, /scan_swing, /export, /status
"""

import asyncio
import logging
from datetime import datetime, timezone

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

import config
from services.data_service import fetch_bulk_data, fetch_intraday_data
from services.scoring_service import run_screening
from services.ticker_service import get_all_tickers, refresh_tickers
from risk.risk_manager import apply_risk_check
from bot.message_formatter import format_signal_message, format_scan_summary
from database.db import get_session
from database.models import Signal, Analysis
from export.excel_export import export_signals_to_excel

logger = logging.getLogger(__name__)

# Lock to prevent concurrent scans
_scan_lock = asyncio.Lock()


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    msg = (
        "🚀 <b>SmartStock Scanner</b> — Ensemble-Kalman Edition\n\n"
        "Sistem screening saham otomatis menggunakan:\n"
        "├ 🔬 Kalman Filter (Signal Processing)\n"
        "├ 📊 MA, RSI, Bollinger Bands (Technical)\n"
        "└ 📈 VBP, VWAP, Candlestick (Volume & Pattern)\n\n"
        "Silakan pilih menu di bawah ini:"
    )
    
    keyboard = [
        ["🔍 Scan Swing", "⚡ Scan Day", "🌅 Scan BSJP"],
        ["📄 Export", "🔄 Refresh Tickers", "📊 Status"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages from custom keyboard."""
    text = update.message.text
    
    if text == "🔍 Scan Swing":
        await cmd_scan(update, context)
    elif text == "⚡ Scan Day":
        await cmd_scan_day(update, context)
    elif text == "🌅 Scan BSJP":
        await cmd_scan_bsjp(update, context)
    elif text == "📄 Export":
        await cmd_export(update, context)
    elif text == "🔄 Refresh Tickers":
        await cmd_refresh(update, context)
    elif text == "📊 Status":
        await cmd_status(update, context)
    else:
        await update.message.reply_text("Silakan gunakan tombol menu yang tersedia di bawah layar Anda.")


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan for Swing Trading signals."""
    await _run_scan(update, config.TRADE_TYPE_SWING)


async def cmd_scan_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan for Day Trading signals."""
    await _run_scan(update, config.TRADE_TYPE_DAY)


async def cmd_scan_bsjp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan for BSJP signals."""
    await _run_scan(update, config.TRADE_TYPE_BSJP)


async def _run_scan(update: Update, trade_type: str):
    """Core scanning logic shared by all scan commands."""
    if _scan_lock.locked():
        await update.message.reply_text(
            "⏳ Scan sedang berjalan. Mohon tunggu hingga selesai."
        )
        return

    async with _scan_lock:
        ticker_list = get_all_tickers()
        await update.message.reply_text(
            f"🔍 Memulai scan <b>{trade_type}</b> untuk {len(ticker_list)} saham...\n"
            f"⏳ Mohon tunggu ~30-60 detik.",
            parse_mode="HTML",
        )

        try:
            # Run heavy I/O in background thread
            loop = asyncio.get_event_loop()
            bulk_data = await loop.run_in_executor(None, fetch_bulk_data)
            intraday_data = await loop.run_in_executor(None, fetch_intraday_data)

            # Run scoring
            results = await loop.run_in_executor(
                None, run_screening, bulk_data, intraday_data, trade_type
            )

            # Apply risk check to each result
            for r in results:
                ticker = r["ticker"]
                if ticker in bulk_data:
                    apply_risk_check(r, bulk_data[ticker])

            # Send summary header
            summary = format_scan_summary(results, trade_type)
            await update.message.reply_text(summary, parse_mode="HTML")

            # Send individual signals (max 10 to avoid spam)
            for r in results[:10]:
                msg = format_signal_message(r)
                await update.message.reply_text(msg, parse_mode="HTML")
                await asyncio.sleep(0.3)  # Rate limit

            # Save to database
            await loop.run_in_executor(None, _save_results_to_db, results)

            if len(results) > 10:
                await update.message.reply_text(
                    f"📋 Menampilkan 10 dari {len(results)} sinyal.\n"
                    f"Gunakan /export untuk melihat semua.",
                    parse_mode="HTML",
                )

        except Exception as e:
            logger.error(f"Scan error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error saat scanning: {e}")


def _save_results_to_db(results: list[dict]):
    """Save screening results to database."""
    session = get_session()
    try:
        for r in results:
            # Save Analysis
            analysis = Analysis(
                ticker=r["ticker"],
                kalman_val=r["kalman"].get("kalman_val"),
                kalman_slope=r["kalman"].get("slope"),
                rsi=r["indicators"].get("rsi"),
                ma_status=r["indicators"].get("ma_status"),
                pattern_name=", ".join(r["volume"].get("patterns", [])),
                score=r["total_score"],
                trade_type=r.get("trade_type"),
                details=r["kalman"].get("details", ""),
            )
            session.add(analysis)

            # Save Signal
            signal = Signal(
                ticker=r["ticker"],
                trade_type=r.get("trade_type"),
                entry=r.get("entry"),
                tp=r.get("tp"),
                sl=r.get("sl"),
                score=r["total_score"],
                risk_pct=r.get("risk_pct"),
            )
            session.add(signal)

        session.commit()
        logger.info(f"Saved {len(results)} results to database.")
    except Exception as e:
        session.rollback()
        logger.error(f"DB save error: {e}")
    finally:
        session.close()


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export signals to Excel and send file."""
    await update.message.reply_text("📄 Generating Excel report...")

    try:
        loop = asyncio.get_event_loop()
        filepath = await loop.run_in_executor(None, export_signals_to_excel)

        if filepath:
            await update.message.reply_document(
                document=open(filepath, "rb"),
                filename=filepath.split("/")[-1],
                caption="📊 SmartStock Scanner — Signal Report",
            )
        else:
            await update.message.reply_text(
                "📭 Belum ada data sinyal. Lakukan /scan terlebih dahulu."
            )
    except Exception as e:
        logger.error(f"Export error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show system status."""
    session = get_session()
    try:
        total_signals = session.query(Signal).count()
        total_analysis = session.query(Analysis).count()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        ticker_count = len(get_all_tickers())

        msg = (
            "📡 <b>System Status</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 Time: {now}\n"
            f"📊 Total Analyses: {total_analysis}\n"
            f"📈 Total Signals: {total_signals}\n"
            f"🎯 Tickers Monitored: {ticker_count}\n"
            f"⚙️ Threshold: Day={config.THRESHOLD_DAY_TRADING} | BSJP={config.THRESHOLD_BSJP} | Swing={config.THRESHOLD_SWING}\n"
            f"🛡️ Risk Limit: {config.MAX_RISK_PERCENT}%\n"
        )
        await update.message.reply_text(msg, parse_mode="HTML")
    finally:
        session.close()


async def cmd_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Refresh the IDX ticker list from external source."""
    await update.message.reply_text("🔄 Refreshing daftar saham dari IDX...")
    try:
        loop = asyncio.get_event_loop()
        count, status_msg = await loop.run_in_executor(None, refresh_tickers)
        await update.message.reply_text(status_msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Refresh error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")

