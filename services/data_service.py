"""
SmartStock Scanner — Data Ingestion Service
Bulk download stock data using yfinance with concurrent processing.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf

import config
from services.ticker_service import get_all_tickers

logger = logging.getLogger(__name__)


def fetch_single_ticker(ticker: str, period: str, interval: str) -> tuple[str, pd.DataFrame]:
    """
    Fetch historical data for a single ticker.
    Returns (ticker, DataFrame) tuple.
    """
    jk_ticker = f"{ticker}.JK" if not ticker.endswith(".JK") else ticker
    try:
        stock = yf.Ticker(jk_ticker)
        df = stock.history(period=period, interval=interval)
        if df.empty:
            logger.warning(f"[{ticker}] No data returned from Yahoo Finance")
            return ticker, pd.DataFrame()

        # Flatten MultiIndex columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Drop rows with NaN in critical OHLCV columns
        ohlcv = ["Open", "High", "Low", "Close", "Volume"]
        existing_cols = [c for c in ohlcv if c in df.columns]
        df = df.dropna(subset=existing_cols)

        if df.empty:
            logger.warning(f"[{ticker}] All rows NaN after cleanup")
            return ticker, pd.DataFrame()

        df["Ticker"] = ticker
        logger.info(f"[{ticker}] Fetched {len(df)} bars")
        return ticker, df
    except Exception as e:
        logger.error(f"[{ticker}] Error fetching data: {e}")
        return ticker, pd.DataFrame()


def fetch_bulk_data(
    tickers: list[str] | None = None,
    period: str = config.DATA_PERIOD,
    interval: str = config.DATA_INTERVAL,
    max_workers: int = 20,
) -> dict[str, pd.DataFrame]:
    """
    Fetch data for multiple tickers concurrently using ThreadPoolExecutor.
    Returns dict of {ticker: DataFrame}.
    """
    if tickers is None:
        tickers = get_all_tickers()

    results: dict[str, pd.DataFrame] = {}

    logger.info(f"Starting bulk download for {len(tickers)} tickers (workers={max_workers})...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_single_ticker, ticker, period, interval): ticker
            for ticker in tickers
        }

        for future in as_completed(futures):
            ticker = futures[future]
            try:
                t, df = future.result()
                if not df.empty:
                    results[t] = df
            except Exception as e:
                logger.error(f"[{ticker}] Future error: {e}")

    logger.info(f"Bulk download complete: {len(results)}/{len(tickers)} tickers successful")
    return results


def fetch_intraday_data(
    tickers: list[str] | None = None,
    max_workers: int = 20,
) -> dict[str, pd.DataFrame]:
    """
    Fetch intraday data (15-minute bars) for VWAP calculation.
    """
    return fetch_bulk_data(
        tickers=tickers,
        period=config.INTRADAY_PERIOD,
        interval=config.INTRADAY_INTERVAL,
        max_workers=max_workers,
    )
