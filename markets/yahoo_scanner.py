"""Market data helpers built on Yahoo Finance."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

from core.config import settings
from core.logger import get_logger
from db.models import AutoWatchlistCandidateModel, MarketMover

logger = get_logger(__name__)

_price_cache: dict[str, tuple[datetime, float]] = {}
_top_movers_cache: dict[str, tuple[datetime, dict[str, list[MarketMover]]]] = {}
_rate_limited_until: datetime | None = None


def _normalize_download(data: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if isinstance(data.columns, pd.MultiIndex):
        try:
            return data.xs(ticker, axis=1, level=0)
        except KeyError:
            return pd.DataFrame()
    return data


def _is_rate_limited(message: str) -> bool:
    return "rate limit" in message.lower() or "too many requests" in message.lower()


def _rate_limit_active() -> bool:
    return _rate_limited_until is not None and datetime.now(timezone.utc) < _rate_limited_until


def _activate_rate_limit_backoff(reason: str) -> None:
    global _rate_limited_until
    _rate_limited_until = datetime.now(timezone.utc) + timedelta(
        seconds=settings.yahoo_rate_limit_cooldown_seconds
    )
    logger.warning(
        "Yahoo rate limit detected. Backing off until %s. Reason: %s",
        _rate_limited_until.isoformat(),
        reason,
    )


def _get_cached_price(ticker: str) -> float | None:
    cached = _price_cache.get(ticker)
    if not cached:
        return None
    cached_at, price = cached
    if datetime.now(timezone.utc) - cached_at <= timedelta(seconds=settings.latest_prices_cache_seconds):
        return price
    return None


def _set_cached_price(ticker: str, price: float) -> None:
    _price_cache[ticker] = (datetime.now(timezone.utc), price)


def _download_single_ticker(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """Download a single ticker safely and normalize the response."""

    if _rate_limit_active():
        logger.info("Skipping download for %s while Yahoo cooldown is active", ticker)
        return pd.DataFrame()

    for attempt in range(1, settings.yahoo_retry_count + 2):
        try:
            frame = yf.download(
                tickers=ticker,
                period=period,
                interval=interval,
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=False,
                timeout=settings.yahoo_timeout_seconds,
            )
            normalized = _normalize_download(frame, ticker).dropna()
            if not normalized.empty:
                return normalized
        except Exception as exc:
            if _is_rate_limited(str(exc)):
                _activate_rate_limit_backoff(str(exc))
                break
            logger.warning(
                "Single-ticker download failed for %s on attempt %s/%s: %s",
                ticker,
                attempt,
                settings.yahoo_retry_count + 1,
                exc,
            )
    return pd.DataFrame()


def _download_many_tickers(
    tickers: list[str],
    *,
    period: str,
    interval: str,
) -> dict[str, pd.DataFrame]:
    """Download many tickers, falling back to per-ticker requests if Yahoo batch mode breaks."""

    if not tickers:
        return {}

    if _rate_limit_active():
        logger.info("Yahoo cooldown active, skipping batch download for %s tickers", len(tickers))
        return {ticker: pd.DataFrame() for ticker in tickers}

    frames: dict[str, pd.DataFrame] = {}

    for start in range(0, len(tickers), settings.yahoo_batch_size):
        chunk = tickers[start : start + settings.yahoo_batch_size]
        try:
            batch = yf.download(
                tickers=chunk,
                period=period,
                interval=interval,
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=False,
                timeout=settings.yahoo_timeout_seconds,
            )
            for ticker in chunk:
                frames[ticker] = _normalize_download(batch, ticker).dropna()
        except Exception as exc:
            if _is_rate_limited(str(exc)):
                _activate_rate_limit_backoff(str(exc))
            logger.warning(
                "Batch download failed for chunk %s, falling back to single-ticker fetches: %s",
                chunk,
                exc,
            )
            for ticker in chunk:
                frames[ticker] = pd.DataFrame()

    missing = [ticker for ticker in tickers if ticker not in frames or frames[ticker].empty]
    for ticker in missing:
        frames[ticker] = _download_single_ticker(ticker, period, interval)

    return frames


def get_latest_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch latest close prices for a list of tickers."""

    if not tickers:
        return {}

    prices: dict[str, float] = {}
    missing_tickers: list[str] = []
    for ticker in tickers:
        cached = _get_cached_price(ticker)
        if cached is None:
            missing_tickers.append(ticker)
        else:
            prices[ticker] = cached

    frames = _download_many_tickers(missing_tickers, period="2d", interval="1m")
    for ticker, frame in frames.items():
        try:
            if frame.empty:
                continue
            price = float(frame["Close"].iloc[-1])
            prices[ticker] = price
            _set_cached_price(ticker, price)
        except Exception as exc:
            logger.warning("Could not fetch latest price for %s: %s", ticker, exc)

    return prices


def compute_top_movers(tickers: list[str], limit: int | None = None) -> dict[str, list[MarketMover]]:
    """Return the top gainers and losers from the watchlist."""

    if not tickers:
        return {"gainers": [], "losers": []}

    cache_key = f"{','.join(sorted(tickers))}:{limit if limit is not None else 'all'}"
    cached = _top_movers_cache.get(cache_key)
    if cached:
        cached_at, payload = cached
        if datetime.now(timezone.utc) - cached_at <= timedelta(seconds=settings.top_movers_cache_seconds):
            return payload

    movers: list[MarketMover] = []
    frames = _download_many_tickers(tickers, period="5d", interval="1d")
    for ticker, frame in frames.items():
        try:
            if frame.empty or len(frame) < 2:
                continue
            # previous_close = float(frame["Close"].iloc[-2])
            # latest_close = float(frame["Close"].iloc[-1])

            open_price = frame["Open"].iloc[-1]
            latest_close = frame["Close"].iloc[-1]
            change_pct = ((latest_close - open_price) / open_price) * 100  # ((latest_close - previous_close) / previous_close) * 100
            movers.append(
                MarketMover(ticker=ticker, price=latest_close, change_pct=round(change_pct, 2))
            )
        except Exception as exc:
            logger.warning("Could not compute mover for %s: %s", ticker, exc)

    sorted_gainers = sorted(
        [item for item in movers if item.change_pct > 0],
        key=lambda item: item.change_pct,
        reverse=True,
    )
    sorted_losers = sorted(
        [item for item in movers if item.change_pct < 0],
        key=lambda item: item.change_pct,
    )
    gainers = sorted_gainers[:limit] if limit is not None else sorted_gainers
    losers = sorted_losers[:limit] if limit is not None else sorted_losers
    payload = {"gainers": gainers, "losers": losers}
    _top_movers_cache[cache_key] = (datetime.now(timezone.utc), payload)
    return payload


def reset_market_data_cache() -> None:
    """Clear cached market data after switching active markets."""

    _price_cache.clear()
    _top_movers_cache.clear()


def analyze_watchlist_candidates(
    tickers: list[str],
    *,
    min_price: float,
    min_avg_volume: float,
) -> list[AutoWatchlistCandidateModel]:
    """Rank a broader market universe into watchlist candidates."""

    if not tickers:
        return []

    candidates: list[AutoWatchlistCandidateModel] = []
    frames = _download_many_tickers(tickers, period="3mo", interval="1d")
    for ticker, frame in frames.items():
        try:
            if frame.empty or len(frame) < 20:
                continue

            closes = frame["Close"].dropna()
            volumes = frame["Volume"].dropna() if "Volume" in frame.columns else pd.Series(dtype=float)
            if closes.empty or volumes.empty:
                continue

            price = float(closes.iloc[-1])
            avg_volume = float(volumes.tail(20).mean())
            # if price < min_price or avg_volume < min_avg_volume:
                # continue

            prev_close = float(closes.iloc[-2])
            change_pct = ((price - prev_close) / prev_close) * 100 if prev_close else 0.0
            trend_pct = ((price - float(closes.iloc[-20])) / float(closes.iloc[-20])) * 100
            dollar_volume_m = (price * avg_volume) / 1_000_000
            score = round((abs(change_pct) * 0.4) + (max(trend_pct, 0.0) * 0.3) + (dollar_volume_m * 0.3), 2)

            candidates.append(
                AutoWatchlistCandidateModel(
                    ticker=ticker,
                    price=round(price, 2),
                    change_pct=round(change_pct, 2),
                    avg_volume=round(avg_volume, 2),
                    score=score,
                )
            )
        except Exception as exc:
            logger.warning("Could not analyze watchlist candidate for %s: %s", ticker, exc)

    return sorted(candidates, key=lambda item: item.score, reverse=True)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
