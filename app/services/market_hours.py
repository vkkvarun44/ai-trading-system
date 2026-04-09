"""Market-hours helpers for scheduler gating."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.dependencies import market_profile_manager
from core.config import settings


def is_regular_market_open(now: datetime | None = None) -> bool:
    """Return whether the active market is open during regular weekday hours."""

    profile = market_profile_manager.get_active_profile()
    market_timezone = ZoneInfo(profile.timezone)
    current = now.astimezone(market_timezone) if now else datetime.now(market_timezone)
    if current.weekday() >= 5:
        return False

    current_time = current.time()
    return profile.open_time <= current_time <= profile.close_time


def get_market_status(now: datetime | None = None) -> dict[str, str | bool | int]:
    """Return market status metadata for the frontend and scheduler."""

    profile = market_profile_manager.get_active_profile()
    market_timezone = ZoneInfo(profile.timezone)
    current = now.astimezone(market_timezone) if now else datetime.now(market_timezone)
    is_open = is_regular_market_open(current)
    status = "OPEN" if is_open else "CLOSED"

    next_open = current
    if is_open:
        next_open = current.replace(
            hour=profile.open_time.hour,
            minute=profile.open_time.minute,
            second=0,
            microsecond=0,
        ) + timedelta(days=1)
    else:
        next_open = current.replace(
            hour=profile.open_time.hour,
            minute=profile.open_time.minute,
            second=0,
            microsecond=0,
        )
        if current.weekday() >= 5:
            next_open += timedelta(days=(7 - current.weekday()))
        elif current.time() > profile.close_time:
            next_open += timedelta(days=1)

    while next_open.weekday() >= 5:
        next_open += timedelta(days=1)

    return {
        "active_market": profile.key,
        "market_name": profile.name,
        "status": status,
        "is_open": is_open,
        "timezone": profile.timezone,
        "current_time": current.isoformat(),
        "next_open": next_open.isoformat(),
        "market_open_time": profile.open_time.isoformat(timespec="minutes"),
        "market_close_time": profile.close_time.isoformat(timespec="minutes"),
        "currency_code": profile.currency_code,
        "currency_locale": profile.currency_locale,
        "watchlist_size": len(profile.watchlist),
    }


def get_latest_completed_session_date(now: datetime | None = None) -> date:
    """Return the most recent regular-session date whose close has passed."""

    profile = market_profile_manager.get_active_profile()
    market_timezone = ZoneInfo(profile.timezone)
    current = now.astimezone(market_timezone) if now else datetime.now(market_timezone)
    session_day = current.date()

    if current.weekday() < 5 and current.time() > profile.close_time:
        return session_day

    session_day -= timedelta(days=1)
    while session_day.weekday() >= 5:
        session_day -= timedelta(days=1)
    return session_day


def should_exit_before_market_close(now: datetime | None = None) -> bool:
    """Return whether the engine should flatten intraday positions."""

    profile = market_profile_manager.get_active_profile()
    market_timezone = ZoneInfo(profile.timezone)
    current = now.astimezone(market_timezone) if now else datetime.now(market_timezone)
    if current.weekday() >= 5:
        return False

    close_at = current.replace(
        hour=profile.close_time.hour,
        minute=profile.close_time.minute,
        second=0,
        microsecond=0,
    )
    cutoff = close_at - timedelta(minutes=settings.end_of_day_exit_buffer_minutes)
    return cutoff <= current <= close_at
