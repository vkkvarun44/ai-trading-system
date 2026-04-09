"""Watchlist preparation, normalization, and persistence."""

from __future__ import annotations

from datetime import datetime, timedelta
import re
from threading import RLock
from zoneinfo import ZoneInfo

from core.config import settings
from db.models import AutoWatchlistCandidateModel, AutoWatchlistResponseModel
from db.persistence import PersistenceManager
from markets.yahoo_universe import get_us_market_universe
from markets.nse_universe import get_india_market_universe

from markets.yahoo_scanner import analyze_watchlist_candidates


_US_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")
_INDIA_PATTERN = re.compile(r"^[A-Z][A-Z0-9&.\-]{0,20}\.(NS|BO)$")


class WatchlistManager:
    """Prepare and persist one watchlist per market."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._watchlists = {
            "US": list(settings.us_watchlist),
            "INDIA": list(settings.india_watchlist),
        }
        self._last_refreshed_at = {"US": None, "INDIA": None}

    def initialize(self, persistence: PersistenceManager) -> None:
        """Load persisted watchlists, falling back to configured defaults."""

        for market in ("US", "INDIA"):
            stored = persistence.load_watchlist(market)
            self._last_refreshed_at[market] = persistence.load_watchlist_refreshed_at(market)
            if stored:
                prepared = stored
            else:
                prepared = self.build_watchlist(market).tickers
                if not prepared:
                    prepared = self.prepare_watchlist(market, self._watchlists[market])[0]
            self.set_watchlist(market, prepared)
            if not stored and prepared:
                persistence.save_watchlist(market, prepared)
                self._last_refreshed_at[market] = persistence.load_watchlist_refreshed_at(market)

    def get_watchlist(self, market: str) -> list[str]:
        with self._lock:
            return list(self._watchlists[market.upper()])

    def get_last_refreshed_at(self, market: str) -> datetime | None:
        with self._lock:
            return self._last_refreshed_at[market.upper()]

    def set_watchlist(self, market: str, tickers: list[str]) -> None:
        with self._lock:
            self._watchlists[market.upper()] = list(tickers)

    def set_last_refreshed_at(self, market: str, refreshed_at: datetime | None) -> None:
        with self._lock:
            self._last_refreshed_at[market.upper()] = refreshed_at

    def prepare_watchlist(self, market: str, raw_tickers: list[str]) -> tuple[list[str], list[str]]:
        """Normalize, validate, and deduplicate raw watchlist inputs."""

        prepared: list[str] = []
        invalid: list[str] = []
        seen: set[str] = set()
        market_key = market.upper()

        for token in self._expand_tokens(raw_tickers):
            normalized = self._normalize_ticker(market_key, token)
            if not normalized or not self._is_valid_ticker(market_key, normalized):
                invalid.append(token.strip())
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            prepared.append(normalized)

        return prepared, invalid

    def save_prepared_watchlist(
        self,
        market: str,
        raw_tickers: list[str],
        persistence: PersistenceManager,
    ) -> tuple[list[str], list[str]]:
        prepared, invalid = self.prepare_watchlist(market, raw_tickers)
        self.set_watchlist(market, prepared)
        persistence.save_watchlist(market, prepared)
        self.set_last_refreshed_at(market, persistence.load_watchlist_refreshed_at(market))
        return prepared, invalid

    def build_watchlist(self, market: str, target_size: int | None = None) -> AutoWatchlistResponseModel:
        """Automatically build a watchlist by scoring a broader market universe."""

        market_key = market.upper()
        universe = self._get_market_universe(market_key)
        target = target_size or settings.auto_watchlist_target_size
        candidates = analyze_watchlist_candidates(
            universe,
            min_price=settings.auto_watchlist_min_price,
            min_avg_volume=settings.auto_watchlist_min_avg_volume,
        )
        selected = candidates[:target]
        return AutoWatchlistResponseModel(
            market=market_key,
            universe_size=len(universe),
            eligible_count=len(candidates),
            target_size=target,
            tickers=[candidate.ticker for candidate in selected],
            candidates=selected,
        )

    def build_and_save_watchlist(
        self,
        market: str,
        persistence: PersistenceManager,
        target_size: int | None = None,
    ) -> AutoWatchlistResponseModel:
        result = self.build_watchlist(market, target_size=target_size)
        self.set_watchlist(market, result.tickers)
        persistence.save_watchlist(market, result.tickers)
        self.set_last_refreshed_at(market, persistence.load_watchlist_refreshed_at(market))
        return result

    def should_refresh_market_watchlist(
        self,
        market: str,
        timezone_name: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Return whether the market watchlist should be rebuilt now."""

        current = now or datetime.now(ZoneInfo(timezone_name))
        last_refreshed_at = self.get_last_refreshed_at(market)
        if last_refreshed_at is None:
            return True

        localized_last_refresh = last_refreshed_at.astimezone(ZoneInfo(timezone_name))
        if localized_last_refresh.date() != current.date():
            return True

        return current - localized_last_refresh >= timedelta(
            seconds=settings.auto_watchlist_refresh_seconds
        )

    def _get_market_universe(self, market: str) -> list[str]:
        if market == "INDIA":
            return get_india_market_universe()
        return get_us_market_universe()

    def _expand_tokens(self, raw_tickers: list[str]) -> list[str]:
        expanded: list[str] = []
        for item in raw_tickers:
            expanded.extend(re.split(r"[\s,;\n]+", item))
        return [item for item in expanded if item and item.strip()]

    def _normalize_ticker(self, market: str, ticker: str) -> str:
        cleaned = ticker.strip().upper().replace(" ", "")
        if not cleaned:
            return ""
        if market == "INDIA" and not cleaned.endswith((".NS", ".BO")):
            return f"{cleaned}.NS"
        if market == "US" and cleaned.endswith((".NS", ".BO")):
            return ""
        return cleaned

    def _is_valid_ticker(self, market: str, ticker: str) -> bool:
        if market == "INDIA":
            return bool(_INDIA_PATTERN.match(ticker))
        return bool(_US_PATTERN.match(ticker))
