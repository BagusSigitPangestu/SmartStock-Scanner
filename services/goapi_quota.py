"""
SmartStock Scanner — GoAPI Quota Manager
Tracks daily API call usage to prevent exceeding the free tier limit (30 req/day).
Resets automatically at midnight.
"""

import logging
from datetime import date
from threading import Lock

logger = logging.getLogger(__name__)

# Daily limit for GoAPI free tier
GOAPI_DAILY_LIMIT = 28  # Conservative buffer below 30

_lock = Lock()
_quota = {
    "date": date.today(),
    "count": 0,
}


def _reset_if_new_day():
    today = date.today()
    if _quota["date"] != today:
        _quota["date"] = today
        _quota["count"] = 0
        logger.info("GoAPI quota reset for new day.")


def can_call() -> bool:
    """Returns True if we still have remaining quota for today."""
    with _lock:
        _reset_if_new_day()
        return _quota["count"] < GOAPI_DAILY_LIMIT


def register_call():
    """Record that one API call was made."""
    with _lock:
        _reset_if_new_day()
        _quota["count"] += 1
        remaining = GOAPI_DAILY_LIMIT - _quota["count"]
        if remaining <= 5:
            logger.warning(f"⚠️ GoAPI quota hampir habis! Sisa: {remaining}/{GOAPI_DAILY_LIMIT} requests hari ini.")
        else:
            logger.debug(f"GoAPI quota used: {_quota['count']}/{GOAPI_DAILY_LIMIT}")


def get_status() -> dict:
    """Return current quota status."""
    with _lock:
        _reset_if_new_day()
        used = _quota["count"]
        remaining = max(0, GOAPI_DAILY_LIMIT - used)
        return {
            "used": used,
            "limit": GOAPI_DAILY_LIMIT,
            "remaining": remaining,
            "date": str(_quota["date"]),
        }
