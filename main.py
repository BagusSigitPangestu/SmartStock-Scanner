"""
SmartStock Scanner — Main Entry Point
Ensemble-Kalman Edition

Runs the Telegram bot with APScheduler for automated scanning.
"""

import os
import sys
import logging
from datetime import datetime

from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, filters

import config
from database.db import init_db
from bot.telegram_bot import (
    cmd_start, cmd_scan, cmd_scan_day, cmd_scan_bsjp,
    cmd_export, cmd_status, cmd_refresh, handle_message
)

# ──────────────────────────────────────────────
# Setup
# ──────────────────────────────────────────────
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("smartstock.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("SmartStock")

# Suppress noisy loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("yfinance").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)


async def setup_scheduler(app: Application):
    """
    Setup APScheduler to auto-scan during market hours.
    Scans every SCAN_INTERVAL_MINUTES between 09:00-15:00 WIB (UTC+7).
    Called as post_init callback (event loop is already running).
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    scheduler = AsyncIOScheduler(timezone="Asia/Jakarta")

    async def scheduled_scan():
        """Run automated scan and send results to configured chat."""
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not chat_id:
            logger.warning("TELEGRAM_CHAT_ID not set. Skipping scheduled scan.")
            return

        logger.info("⏰ Running scheduled scan...")

        try:
            from services.data_service import fetch_bulk_data, fetch_intraday_data
            from services.scoring_service import run_screening
            from risk.risk_manager import apply_risk_check
            from bot.message_formatter import format_signal_message, format_scan_summary
            from bot.telegram_bot import _save_results_to_db

            loop = asyncio.get_event_loop()
            bulk_data = await loop.run_in_executor(None, fetch_bulk_data)
            intraday_data = await loop.run_in_executor(None, fetch_intraday_data)

            # Determine trade type based on time
            now = datetime.now()
            if now.hour >= 14:
                trade_type = config.TRADE_TYPE_BSJP
            else:
                trade_type = config.TRADE_TYPE_DAY

            results = await loop.run_in_executor(
                None, run_screening, bulk_data, intraday_data, trade_type
            )

            valid_results = []
            for r in results:
                ticker = r["ticker"]
                if ticker in bulk_data:
                    apply_risk_check(r, bulk_data[ticker])
                    if r.get("rrr", 0) >= 2.0:
                        valid_results.append(r)
            results = valid_results

            if results:
                summary = format_scan_summary(results, trade_type)
                await app.bot.send_message(
                    chat_id=chat_id, text=summary, parse_mode="HTML"
                )

                for r in results[:10]:
                    msg = format_signal_message(r)
                    await app.bot.send_message(
                        chat_id=chat_id, text=msg, parse_mode="HTML"
                    )
                    await asyncio.sleep(0.3)

                await loop.run_in_executor(None, _save_results_to_db, results)

            logger.info(f"Scheduled scan done: {len(results)} signals sent.")

        except Exception as e:
            logger.error(f"Scheduled scan error: {e}", exc_info=True)

    # Schedule: every N minutes during market hours (Mon-Fri)
    scheduler.add_job(
        scheduled_scan,
        CronTrigger(
            day_of_week="mon-fri",
            hour=f"{config.MARKET_OPEN_HOUR}-{config.MARKET_CLOSE_HOUR - 1}",
            minute=f"*/{config.SCAN_INTERVAL_MINUTES}",
            timezone="Asia/Jakarta",
        ),
        id="market_scan",
        name="Market Hours Scan",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        f"📅 Scheduler active: scanning every {config.SCAN_INTERVAL_MINUTES}min "
        f"({config.MARKET_OPEN_HOUR:02d}:00-{config.MARKET_CLOSE_HOUR:02d}:00 WIB, Mon-Fri)"
    )


def main():
    """Start the SmartStock Scanner bot."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token == "your_telegram_bot_token_here":
        logger.error("❌ TELEGRAM_BOT_TOKEN belum diisi! Edit file .env terlebih dahulu.")
        sys.exit(1)

    # Initialize database
    init_db()
    logger.info("✅ Database initialized.")

    # Create exports directory
    os.makedirs("exports", exist_ok=True)

    # Build Telegram bot application
    app = Application.builder().token(token).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(CommandHandler("scan_day", cmd_scan_day))
    app.add_handler(CommandHandler("scan_bsjp", cmd_scan_bsjp))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("refresh", cmd_refresh))
    app.add_handler(CommandHandler("status", cmd_status))

    # Text message handler for custom keyboard
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Setup scheduled scanning via post_init (event loop will be running)
    app.post_init = setup_scheduler

    logger.info("🚀 SmartStock Scanner is running! Press Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
