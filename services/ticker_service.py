"""
SmartStock Scanner — Ticker Service
Dynamically fetches full IDX (Indonesia Stock Exchange) ticker list.
Caches locally and falls back to hardcoded config if fetch fails.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

import config

logger = logging.getLogger(__name__)

CACHE_FILE = Path("cache/idx_tickers.json")
CACHE_MAX_AGE_DAYS = 7  # Refresh cache weekly


def get_all_tickers() -> list[str]:
    """
    Get the full list of IDX tickers.
    Priority: fresh fetch > cache > hardcoded fallback.
    """
    # Try cache first (fast path)
    cached = _load_cache()
    if cached:
        logger.info(f"Using cached ticker list: {len(cached)} tickers")
        return cached

    # Try fetching fresh list
    fetched = _fetch_idx_tickers()
    if fetched:
        _save_cache(fetched)
        logger.info(f"Fetched fresh ticker list: {len(fetched)} tickers")
        return fetched

    # Fallback to hardcoded
    logger.warning(f"Using hardcoded fallback: {len(config.IDX_TICKERS)} tickers")
    return config.IDX_TICKERS


def refresh_tickers() -> tuple[int, str]:
    """
    Force refresh the ticker list.
    Uses yfinance discovery to validate tickers from the seed list + existing cache.
    Returns (count, status_message).
    """
    # Combine hardcoded + any existing cache for comprehensive seed
    seed = set(config.IDX_TICKERS)
    existing = _load_cache()
    if existing:
        seed.update(existing)

    valid = _discover_via_yfinance(sorted(seed))
    if valid:
        _save_cache(valid)
        return len(valid), f"✅ Berhasil refresh: {len(valid)} saham aktif ditemukan"

    count = len(existing) if existing else len(config.IDX_TICKERS)
    return count, f"⚠️ Gagal refresh, menggunakan data sebelumnya: {count} saham"


def _fetch_idx_tickers() -> list[str]:
    """
    Fetch IDX ticker list from public sources.
    Tries multiple sources for reliability.
    """
    tickers = set()

    # Method 1: IDX Stock List via public JSON endpoints
    try:
        url = "https://www.idx.co.id/primary/StockData/GetSecuritiesStock"
        params = {
            "start": 0,
            "length": 9999,
            "code": "",
            "sector": "",
            "board": "",
        }
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.idx.co.id/id/data-pasar/data-saham/daftar-saham/",
        }
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data", data.get("replies", []))
            if isinstance(items, list):
                for item in items:
                    code = item.get("Code", item.get("code", item.get("KodeEmiten", "")))
                    if code and isinstance(code, str) and len(code) <= 6:
                        tickers.add(code.strip().upper())
            if tickers:
                logger.info(f"IDX API: fetched {len(tickers)} tickers")
    except Exception as e:
        logger.warning(f"IDX API failed: {e}")

    # Method 2: Scrape from alternative sources if Method 1 fails
    if not tickers:
        try:
            url = "https://www.idx.co.id/primary/ListedCompany/GetCompanyProfiles"
            params = {"start": 0, "length": 9999}
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.idx.co.id/",
            }
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("data", data.get("replies", []))
                if isinstance(items, list):
                    for item in items:
                        code = item.get("KodeEmiten", item.get("Code", ""))
                        if code and isinstance(code, str) and len(code) <= 6:
                            tickers.add(code.strip().upper())
                if tickers:
                    logger.info(f"IDX Company API: fetched {len(tickers)} tickers")
        except Exception as e:
            logger.warning(f"IDX Company API failed: {e}")

    # Sort and return
    if tickers:
        return sorted(tickers)

    return []


def _discover_via_yfinance(seed_list: list[str], batch_size: int = 50) -> list[str]:
    """
    Validate tickers against Yahoo Finance by batch-downloading 1 day of data.
    Returns list of tickers that have active price data.
    """
    import yfinance as yf
    import pandas as pd
    import time

    valid = set()
    total = len(seed_list)

    for i in range(0, total, batch_size):
        batch = seed_list[i:i + batch_size]
        jk_batch = " ".join(f"{t}.JK" for t in batch)

        try:
            data = yf.download(jk_batch, period="1d", progress=False, threads=True)
            if not data.empty and isinstance(data.columns, pd.MultiIndex):
                for ticker_jk in set(data.columns.get_level_values(1)):
                    col = ("Close", ticker_jk)
                    if col in data.columns and data[col].notna().any():
                        valid.add(ticker_jk.replace(".JK", ""))
        except Exception as e:
            logger.warning(f"yfinance batch {i} error: {e}")

        time.sleep(0.2)

    logger.info(f"yfinance discovery: {len(valid)}/{total} valid tickers")
    return sorted(valid) if valid else []



def _load_cache() -> list[str] | None:
    """Load tickers from local cache if fresh enough."""
    try:
        if not CACHE_FILE.exists():
            return None

        with open(CACHE_FILE, "r") as f:
            data = json.load(f)

        cached_at = datetime.fromisoformat(data.get("cached_at", "2000-01-01"))
        age_days = (datetime.now(timezone.utc) - cached_at.replace(tzinfo=timezone.utc)).days

        if age_days > CACHE_MAX_AGE_DAYS:
            logger.info(f"Cache expired ({age_days} days old)")
            return None

        tickers = data.get("tickers", [])
        if tickers:
            return tickers

    except Exception as e:
        logger.warning(f"Cache load error: {e}")

    return None


def _save_cache(tickers: list[str]):
    """Save tickers to local cache file."""
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "count": len(tickers),
            "tickers": tickers,
        }
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Cached {len(tickers)} tickers to {CACHE_FILE}")
    except Exception as e:
        logger.warning(f"Cache save error: {e}")
