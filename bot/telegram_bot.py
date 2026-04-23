"""
SmartStock Scanner — Telegram Bot Handlers
Commands: /start, /scan, /scan_bsjp, /scan_swing, /export, /status
"""

import asyncio
import logging
from datetime import datetime, timezone

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from services.data_service import fetch_bulk_data, fetch_intraday_data
from services.scoring_service import run_screening
from services.ticker_service import get_all_tickers, refresh_tickers
from risk.risk_manager import apply_risk_check
from bot.message_formatter import format_signal_message, format_scan_summary
from services.broker_service import fetch_broker_summary, format_broker_summary_message, is_stock_fca_or_x
from services.goapi_quota import get_status as get_quota_status
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
    elif text.startswith("/broker ") or text.upper().startswith("BROKER "):
        await cmd_broker(update, context, text.split(" ")[1])
    else:
        await update.message.reply_text("Silakan gunakan tombol menu yang tersedia di bawah layar Anda. Atau ketik '/broker <ticker>' untuk cek bandarmologi.")


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

            # Apply risk check to each result and filter by RRR >= 2.0 (no API calls)
            rrr_passed = []
            for r in results:
                ticker = r["ticker"]
                if ticker in bulk_data:
                    apply_risk_check(r, bulk_data[ticker])
                    if r.get("rrr", 0) >= 2.0:
                        rrr_passed.append(r)

            # FCA/X check for top 5 only (quota-aware)
            valid_results = []
            for r in rrr_passed[:5]:
                ticker = r["ticker"]
                is_fca = await loop.run_in_executor(None, is_stock_fca_or_x, ticker)
                if is_fca:
                    logger.info(f"Skipping {ticker} due to X notation or FCA.")
                    continue
                valid_results.append(r)

            # Deep scan (Broker Summary) only for top 3 — conserve quota
            quota = get_quota_status()
            logger.info(f"GoAPI quota: {quota['used']}/{quota['limit']} used, {quota['remaining']} remaining.")
            for r in valid_results[:3]:
                ticker = r["ticker"]
                broker_data = await loop.run_in_executor(None, fetch_broker_summary, ticker)
                r["broker_summary"] = broker_data

            results = valid_results

            # Send summary header
            summary = format_scan_summary(results, trade_type)
            await update.message.reply_text(summary, parse_mode="HTML")

            # Send individual signals (max 10 to avoid spam)
            for r in results[:10]:
                msg = format_signal_message(r)
                ticker = r["ticker"]
                keyboard = [[InlineKeyboardButton(f"🕵️ Cek Bandar {ticker}", callback_data=f"broker_{ticker}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(msg, parse_mode="HTML", reply_markup=reply_markup)
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
        quota = get_quota_status()

        msg = (
            "📡 <b>System Status</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 Time: {now}\n"
            f"📊 Total Analyses: {total_analysis}\n"
            f"📈 Total Signals: {total_signals}\n"
            f"🎯 Tickers Monitored: {ticker_count}\n"
            f"⚙️ Threshold: Day={config.THRESHOLD_DAY_TRADING} | BSJP={config.THRESHOLD_BSJP} | Swing={config.THRESHOLD_SWING}\n"
            f"🛡️ Risk Limit: {config.MAX_RISK_PERCENT}%\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔌 GoAPI Quota: {quota['used']}/{quota['limit']} digunakan, sisa {quota['remaining']} (reset besok)\n"
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


async def cmd_broker(update: Update, context: ContextTypes.DEFAULT_TYPE, ticker: str = None):
    """Handle on-demand broker summary fetch."""
    if not ticker:
        if context.args:
            ticker = context.args[0]
        else:
            await update.message.reply_text("Silakan masukkan kode saham. Contoh: /broker ASII")
            return

    await update.message.reply_text(f"🔍 Mengambil data Broker Summary untuk {ticker.upper()} via GoAPI...")
    
    try:
        loop = asyncio.get_event_loop()
        summary_data = await loop.run_in_executor(None, fetch_broker_summary, ticker)
        
        msg = format_broker_summary_message(ticker.upper(), summary_data)
        await update.message.reply_text(msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Broker command error: {e}")
        await update.message.reply_text(f"❌ Error mengambil data: {e}")


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("broker_"):
        ticker = data.split("_")[1]
        
        # Send loading message
        loading_msg = await query.message.reply_text(f"🔍 Mengambil data Broker Summary untuk {ticker.upper()} via GoAPI...")
        
        try:
            loop = asyncio.get_event_loop()
            summary_data = await loop.run_in_executor(None, fetch_broker_summary, ticker)
            
            msg = format_broker_summary_message(ticker.upper(), summary_data)
            
            # Edit the loading message with the result
            await loading_msg.edit_text(msg, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Broker callback error: {e}")
            await loading_msg.edit_text(f"❌ Error mengambil data: {e}")

