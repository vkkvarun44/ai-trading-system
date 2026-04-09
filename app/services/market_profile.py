"""Active market configuration and runtime switching."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from datetime import time
from threading import RLock

from core.config import settings


@dataclass(frozen=True, slots=True)
class MarketProfile:
    key: str
    name: str
    timezone: str
    open_time: time
    close_time: time
    currency_code: str
    currency_locale: str
    watchlist: list[str]


class MarketProfileManager:
    """Store and switch the active market profile at runtime."""

    def __init__(self) -> None:
        self._profiles = {
            "US": MarketProfile(
                key="US",
                name="United States",
                timezone="America/New_York",
                open_time=time.fromisoformat("09:30:00"),
                close_time=time.fromisoformat("16:00:00"),
                currency_code="USD",
                currency_locale="en-US",
                watchlist=settings.us_watchlist,
            ),
            "INDIA": MarketProfile(
                key="INDIA",
                name="India",
                timezone="Asia/Kolkata",
                open_time=time.fromisoformat("09:15:00"),
                close_time=time.fromisoformat("15:30:00"),
                currency_code="INR",
                currency_locale="en-IN",
                watchlist=settings.india_watchlist,
            ),
        }
        self._lock = RLock()
        self._active_market = settings.active_market if settings.active_market in self._profiles else "US"

    def get_active_profile(self) -> MarketProfile:
        with self._lock:
            return self._profiles[self._active_market]

    def set_active_market(self, market: str) -> MarketProfile:
        market_key = market.strip().upper()
        with self._lock:
            if market_key not in self._profiles:
                raise ValueError(f"Unsupported market '{market}'.")
            self._active_market = market_key
            return self._profiles[market_key]

    def set_watchlist(self, market: str, tickers: list[str]) -> None:
        market_key = market.strip().upper()
        with self._lock:
            if market_key not in self._profiles:
                raise ValueError(f"Unsupported market '{market}'.")
            self._profiles[market_key] = replace(self._profiles[market_key], watchlist=list(tickers))
