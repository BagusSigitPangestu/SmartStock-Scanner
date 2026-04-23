"""
SmartStock Scanner — Broker Summary Service (GoAPI)
Handles "Deep Scan" requests for top-ranked stocks to fetch real bandarmologi data.
"""

import os
import logging
import requests
from datetime import date, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from services.goapi_quota import can_call, register_call, get_status

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# HTTP Session with Retry
# ──────────────────────────────────────────────

def get_requests_session() -> requests.Session:
    """Create a requests Session with automatic retry on transient errors."""
    session = requests.Session()
    retry = Retry(
        total=3,
        read=3,
        connect=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


# ──────────────────────────────────────────────
# FCA / X Notation Check
# ──────────────────────────────────────────────

def is_stock_fca_or_x(ticker: str) -> bool:
    """
    Returns True if the stock has X notation or is in Full Call Auction (FCA) board.
    Uses GoAPI quota — only called if quota remains.
    """
    api_key = os.getenv("GOAPI_KEY")
    if not api_key:
        return False

    if not can_call():
        logger.warning(f"GoAPI quota habis — skip FCA check untuk {ticker}.")
        return False

    url = f"https://api.goapi.io/stock/idx/{ticker.upper()}/profile"
    params = {"api_key": api_key}

    try:
        session = get_requests_session()
        response = session.get(url, params=params, timeout=10)
        register_call()

        if response.status_code == 200:
            resp_json = response.json()
            if resp_json.get("status") == "success":
                data = resp_json.get("data", {})

                # Check special notations
                notations = data.get("special_notations", [])
                for n in notations:
                    if n.get("notation", "").upper() == "X":
                        logger.info(f"{ticker} memiliki notasi X — diskualifikasi.")
                        return True

                # Check board
                board = data.get("board", "").upper()
                if "PEMANTAUAN KHUSUS" in board or "FCA" in board:
                    logger.info(f"{ticker} berada di papan FCA — diskualifikasi.")
                    return True

        return False

    except requests.exceptions.Timeout:
        logger.warning(f"Timeout saat cek notasi {ticker} — diasumsikan aman (False).")
        return False
    except Exception as e:
        logger.error(f"Error checking notation for {ticker}: {e}")
        return False


# ──────────────────────────────────────────────
# Broker Summary Fetch
# ──────────────────────────────────────────────

def _get_last_trading_date() -> str:
    """
    Returns the most recent weekday date as 'YYYY-MM-DD'.
    Skips weekends. Does NOT skip national holidays (GoAPI returns empty for those).
    """
    from datetime import datetime
    import pytz
    wib = pytz.timezone("Asia/Jakarta")
    d = datetime.now(wib).date()
    # If before market open, step back 1 day
    if datetime.now(wib).hour < 9:
        d -= timedelta(days=1)
    # Step back past weekends
    for _ in range(7):
        if d.weekday() < 5:
            return d.strftime("%Y-%m-%d")
        d -= timedelta(days=1)
    return date.today().strftime("%Y-%m-%d")


def _find_latest_data_date(ticker: str, api_key: str, start_date: str) -> str:
    """
    Try up to 5 consecutive trading days back to find the most recent date with data.
    Returns date string or None.
    """
    from datetime import datetime
    d = datetime.strptime(start_date, "%Y-%m-%d").date()
    headers = {"X-API-KEY": api_key, "Accept": "application/json"}
    session = get_requests_session()

    for _ in range(7):
        if d.weekday() < 5:
            try:
                params = {"api_key": api_key, "date": d.strftime("%Y-%m-%d")}
                r = session.get(
                    f"https://api.goapi.io/stock/idx/{ticker}/broker_summary",
                    params=params, headers=headers, timeout=15
                )
                register_call()
                data = r.json()
                if data.get("status") == "success" and data.get("data", {}).get("results"):
                    return d.strftime("%Y-%m-%d")
            except Exception:
                pass
        d -= timedelta(days=1)
    return None


def fetch_broker_summary(ticker: str, date_str: str = None) -> dict:
    """
    Fetch broker summary data from GoAPI for a specific ticker.
    On-Demand only — checks daily quota before making the call.
    Auto-detects last trading date if date_str not provided.
    """
    api_key = os.getenv("GOAPI_KEY")
    if not api_key:
        logger.warning("GOAPI_KEY not found in environment variables.")
        return {"error": "GOAPI_KEY belum dikonfigurasi di .env"}

    if not can_call():
        status = get_status()
        logger.warning(f"GoAPI quota habis untuk hari ini ({status['used']}/{status['limit']}).")
        return {
            "error": (
                f"⛔ Kuota GoAPI harian habis ({status['used']}/{status['limit']} requests). "
                f"Akan reset besok pagi."
            )
        }

    ticker = ticker.upper()
    # Always include a date — use last trading day if not specified
    if not date_str:
        date_str = _get_last_trading_date()

    url = f"https://api.goapi.io/stock/idx/{ticker}/broker_summary"
    params = {"api_key": api_key, "date": date_str}
    headers = {"X-API-KEY": api_key, "Accept": "application/json"}

    try:
        session = get_requests_session()
        response = session.get(url, params=params, headers=headers, timeout=20)
        register_call()

        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                results = data.get("data", {}).get("results", [])
                if not results:
                    # Auto-fallback: cari hari trading sebelumnya yang ada datanya
                    logger.info(f"{ticker}: data kosong untuk {date_str}, mencoba hari sebelumnya...")
                    from datetime import datetime as dt
                    prev = (dt.strptime(date_str, "%Y-%m-%d").date() - timedelta(days=1)).strftime("%Y-%m-%d")
                    fallback_date = _find_latest_data_date(ticker, api_key, prev)
                    if fallback_date:
                        return fetch_broker_summary(ticker, date_str=fallback_date)
                    return {"error": f"Tidak ada data broker untuk {ticker} dalam 5 hari terakhir."}
                return {"success": True, "data": data.get("data", {}), "date_used": date_str}
            else:
                msg = data.get("message", "Unknown API error")
                return {"error": f"API Error: {msg}"}

        elif response.status_code == 401:
            return {"error": "API Key tidak valid atau kuota gratis harian telah habis."}
        elif response.status_code == 404:
            return {"error": f"Data broker summary tidak ditemukan untuk {ticker}."}
        else:
            return {"error": f"HTTP Error {response.status_code}"}

    except requests.exceptions.Timeout:
        logger.error(f"Timeout saat ambil broker summary {ticker} dari GoAPI.")
        return {"error": f"Request timeout untuk {ticker}. GoAPI mungkin sedang lambat, coba lagi nanti."}
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error fetching broker summary for {ticker}: {e}")
        return {"error": "Terjadi kesalahan jaringan saat menghubungi GoAPI."}
    except Exception as e:
        logger.error(f"Unexpected error in broker_service: {e}")
        return {"error": "Terjadi kesalahan sistem internal."}


# ──────────────────────────────────────────────
# Stockbit Order Book
# ──────────────────────────────────────────────

def fetch_stockbit_orderbook(ticker: str) -> dict:
    """Fetch real-time orderbook data from Stockbit API using Session Token."""
    token = os.getenv("STOCKBIT_TOKEN")
    if not token:
        return {"error": "STOCKBIT_TOKEN belum dikonfigurasi di .env"}

    url = f"https://exodus.stockbit.com/company-price-feed/v2/orderbook/companies/{ticker.upper()}"
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {token}",
        "origin": "https://stockbit.com",
        "referer": "https://stockbit.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }

    try:
        session = get_requests_session()
        response = session.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            return {"success": True, "data": response.json().get("data", {})}
        elif response.status_code == 401:
            return {"error": "STOCKBIT_TOKEN kedaluwarsa atau tidak valid."}
        else:
            return {"error": f"HTTP Error {response.status_code}"}
    except requests.exceptions.Timeout:
        return {"error": "Timeout saat menghubungi Stockbit."}
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching Stockbit orderbook for {ticker}: {e}")
        return {"error": "Terjadi kesalahan jaringan saat menghubungi Stockbit."}


# ──────────────────────────────────────────────
# Adimology Helpers
# ──────────────────────────────────────────────

def get_fraksi(harga: float) -> int:
    if harga < 200: return 1
    if harga < 500: return 2
    if harga < 2000: return 5
    if harga < 5000: return 10
    return 25


def calculate_adimology_targets(
    rata_rata_bandar: float,
    barang_bandar: float,
    ara: float,
    arb: float,
    total_bid: float,
    total_offer: float,
    harga: float,
) -> dict:
    fraksi = get_fraksi(harga)

    # Total Papan = (ARA - ARB) / Fraksi
    total_papan = (ara - arb) / fraksi if fraksi > 0 else 1
    if total_papan <= 0:
        total_papan = 1

    # Rata rata Bid Offer = (Total Bid + Total Offer) / Total Papan
    rata_rata_bid_ofer = (total_bid + total_offer) / total_papan
    if rata_rata_bid_ofer <= 0:
        rata_rata_bid_ofer = 1

    # a = Rata rata bandar * 5%
    a = rata_rata_bandar * 0.05

    # p = Barang Bandar / Rata rata Bid Offer
    p = barang_bandar / rata_rata_bid_ofer if rata_rata_bid_ofer > 0 else 0

    # Target Realistis = Rata rata bandar + a + (p/2 * Fraksi)
    target_realistis = rata_rata_bandar + a + ((p / 2) * fraksi)

    # Target Max = Rata rata bandar + a + (p * Fraksi)
    target_max = rata_rata_bandar + a + (p * fraksi)

    return {
        "fraksi": fraksi,
        "total_papan": round(total_papan),
        "rata_rata_bid_ofer": round(rata_rata_bid_ofer),
        "a": round(a),
        "p": round(p),
        "target_realistis": round(target_realistis),
        "target_max": round(target_max),
    }


# ──────────────────────────────────────────────
# Message Formatter
# ──────────────────────────────────────────────

def _parse_broker_results(results: list) -> tuple[list, list]:
    """
    Parse GoAPI results list into (buyers, sellers) sorted by lot.
    GoAPI structure per item:
      {code, date, side, lot, value, avg, symbol, broker: {code, name}}
    """
    buyers = [r for r in results if r.get("side", "").upper() == "BUY"]
    sellers = [r for r in results if r.get("side", "").upper() == "SELL"]
    buyers.sort(key=lambda x: float(x.get("lot", 0)), reverse=True)
    sellers.sort(key=lambda x: float(x.get("lot", 0)), reverse=True)
    return buyers, sellers


def format_broker_summary_message(ticker: str, summary_data: dict) -> str:
    """
    Formats the GoAPI broker summary data into a Telegram-friendly HTML message.
    GoAPI field names: code, lot, avg, side, broker.name
    """
    if "error" in summary_data:
        return f"⚠️ <b>Broker Summary {ticker}</b>\n<i>{summary_data['error']}</i>"

    data = summary_data.get("data", {})
    if not data:
        return f"⚠️ <b>Broker Summary {ticker}</b>\n<i>Data kosong.</i>"

    results_list = data.get("results", [])
    date_used = summary_data.get("date_used", data.get("date", "N/A"))

    msg = f"📊 <b>Broker Summary {ticker} ({date_used})</b>\n\n"

    if not results_list:
        msg += "<i>Tidak ada data broker yang tersedia.</i>"
    else:
        buyers, sellers = _parse_broker_results(results_list)

        msg += "🟢 <b>Top 5 Buyers:</b>\n"
        for i, b in enumerate(buyers[:5]):
            code = b.get("code", "-")
            name = b.get("broker", {}).get("name", "") if isinstance(b.get("broker"), dict) else ""
            lot = int(b.get("lot", 0))
            avg = float(b.get("avg", 0))
            msg += f"{i+1}. <b>{code}</b> {name}: {lot:,} lot @ {avg:,.0f}\n"

        msg += "\n🔴 <b>Top 5 Sellers:</b>\n"
        for i, s in enumerate(sellers[:5]):
            code = s.get("code", "-")
            name = s.get("broker", {}).get("name", "") if isinstance(s.get("broker"), dict) else ""
            lot = int(s.get("lot", 0))
            avg = float(s.get("avg", 0))
            msg += f"{i+1}. <b>{code}</b> {name}: {lot:,} lot @ {avg:,.0f}\n"

        # Adimology using top buyer
        if buyers:
            top_buyer = buyers[0]
            rata_rata_bandar = float(top_buyer.get("avg", 0))
            barang_bandar = float(top_buyer.get("lot", 0))
            code = top_buyer.get("code", "-")

            ob_res = fetch_stockbit_orderbook(ticker)
            if ob_res.get("success"):
                ob_data = ob_res.get("data", {})
                try:
                    harga = float(ob_data.get("close", 0))
                    ara_val = ob_data.get("ara", {}).get("value", 0) if isinstance(ob_data.get("ara"), dict) else ob_data.get("ara", 0)
                    arb_val = ob_data.get("arb", {}).get("value", 0) if isinstance(ob_data.get("arb"), dict) else ob_data.get("arb", 0)
                    tbo = ob_data.get("total_bid_offer", {})
                    bid_str = tbo.get("bid", {}).get("lot", "0") if isinstance(tbo.get("bid"), dict) else str(tbo.get("bid", "0"))
                    offer_str = tbo.get("offer", {}).get("lot", "0") if isinstance(tbo.get("offer"), dict) else str(tbo.get("offer", "0"))
                    total_bid = float(str(bid_str).replace(",", ""))
                    total_offer = float(str(offer_str).replace(",", ""))
                    if harga > 0 and rata_rata_bandar > 0:
                        targets = calculate_adimology_targets(
                            rata_rata_bandar, barang_bandar, float(ara_val), float(arb_val), total_bid, total_offer, harga
                        )
                        msg += f"\n🎯 <b>Adimology Targets (Acuan: {code})</b>\n"
                        msg += f"Avg Bandar  : {rata_rata_bandar:,.0f}\n"
                        msg += f"Kekuatan (p): {targets['p']:,.2f}\n"
                        msg += f"<b>Target R1   : {targets['target_realistis']:,.0f}</b>\n"
                        msg += f"<b>Target Max  : {targets['target_max']:,.0f}</b>\n"
                except Exception as e:
                    logger.error(f"Error parse adimology for {ticker}: {e}")
            elif "error" in ob_res and "belum dikonfigurasi" not in ob_res["error"]:
                msg += f"\n<i>⚠️ Adimology: {ob_res['error']}</i>\n"

    status = get_status()
    msg += f"\n<i>💡 GoAPI — Sisa kuota: {status['remaining']}/{status['limit']} requests hari ini.</i>"
    return msg

