"""Market-hours helpers for scheduler gating."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.config import settings

MARKET_TIMEZONE = ZoneInfo(settings.market_timezone)


def is_regular_market_open(now: datetime | None = None) -> bool:
    """Return whether the U.S. market is open during regular weekday hours."""

    current = now.astimezone(MARKET_TIMEZONE) if now else datetime.now(MARKET_TIMEZONE)
    if current.weekday() >= 5:
        return False

    current_time = current.time()
    return settings.market_open_time <= current_time <= settings.market_close_time


def get_market_status(now: datetime | None = None) -> dict[str, str | bool]:
    """Return market status metadata for the frontend and scheduler."""

    current = now.astimezone(MARKET_TIMEZONE) if now else datetime.now(MARKET_TIMEZONE)
    is_open = is_regular_market_open(current)
    status = "OPEN" if is_open else "CLOSED"

    next_open = current
    if is_open:
        next_open = current.replace(
            hour=settings.market_open_time.hour,
            minute=settings.market_open_time.minute,
            second=0,
            microsecond=0,
        ) + timedelta(days=1)
    else:
        next_open = current.replace(
            hour=settings.market_open_time.hour,
            minute=settings.market_open_time.minute,
            second=0,
            microsecond=0,
        )
        if current.weekday() >= 5:
            next_open += timedelta(days=(7 - current.weekday()))
        elif current.time() > settings.market_close_time:
            next_open += timedelta(days=1)

    while next_open.weekday() >= 5:
        next_open += timedelta(days=1)

    return {
        "status": status,
        "is_open": is_open,
        "timezone": settings.market_timezone,
        "current_time": current.isoformat(),
        "next_open": next_open.isoformat(),
    }
