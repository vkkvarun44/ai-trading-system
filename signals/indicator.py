"""Indicator calculations for the strategy engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import yfinance as yf
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator

from core.config import settings
from core.logger import get_logger

logger = get_logger(__name__)

_indicator_cache: dict[str, tuple[datetime, dict[str, float]]] = {}
_indicator_backoff_until: datetime | None = None


def _as_price_series(data: pd.DataFrame | pd.Series) -> pd.Series:
    """Normalize Yahoo output into a 1D close-price series."""

    if isinstance(data, pd.Series):
        return data.dropna()

    if isinstance(data, pd.DataFrame):
        if "Close" in data.columns:
            close = data["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            return close.dropna()

        if isinstance(data.columns, pd.MultiIndex):
            close_columns = [column for column in data.columns if column[-1] == "Close"]
            if close_columns:
                close = data[close_columns[0]]
                if isinstance(close, pd.DataFrame):
                    close = close.iloc[:, 0]
                return close.dropna()

    return pd.Series(dtype=float)


def _as_float(value: object) -> float:
    """Convert a scalar-like pandas value into a plain float."""

    if isinstance(value, pd.Series):
        return float(value.iloc[0])
    return float(value)


def _is_rate_limited(message: str) -> bool:
    return "rate limit" in message.lower() or "too many requests" in message.lower()


def _rate_limit_active() -> bool:
    return _indicator_backoff_until is not None and datetime.now(timezone.utc) < _indicator_backoff_until


def _activate_rate_limit_backoff(reason: str) -> None:
    global _indicator_backoff_until
    _indicator_backoff_until = datetime.now(timezone.utc) + timedelta(
        seconds=settings.yahoo_rate_limit_cooldown_seconds
    )
    logger.warning(
        "Indicator downloads backing off until %s due to Yahoo rate limiting: %s",
        _indicator_backoff_until.isoformat(),
        reason,
    )


def get_indicators(ticker: str) -> dict[str, float] | None:
    """Fetch and calculate indicators for a ticker."""

    cached = _indicator_cache.get(ticker)
    if cached:
        cached_at, payload = cached
        if datetime.now(timezone.utc) - cached_at <= timedelta(seconds=settings.indicators_cache_seconds):
            return payload

    if _rate_limit_active():
        logger.info("Skipping indicator refresh for %s while Yahoo cooldown is active", ticker)
        return cached[1] if cached else None

    df = pd.DataFrame()
    for attempt in range(1, settings.yahoo_retry_count + 2):
        try:
            df = yf.download(
                ticker,
                period="1mo",
                interval="1h",
                auto_adjust=False,
                progress=False,
                threads=False,
                timeout=settings.yahoo_timeout_seconds,
            ).dropna()
            if not df.empty:
                break
        except Exception as exc:
            if _is_rate_limited(str(exc)):
                _activate_rate_limit_backoff(str(exc))
                break
            logger.warning(
                "Indicator download failed for %s on attempt %s/%s: %s",
                ticker,
                attempt,
                settings.yahoo_retry_count + 1,
                exc,
            )

    if df.empty or len(df) < 25:
        return None

    close = _as_price_series(df)
    if close.empty or len(close) < 25:
        return None

    df = df.copy()
    df["Close"] = close
    df["rsi"] = RSIIndicator(close=close, window=14).rsi()
    df["ema_9"] = EMAIndicator(close=close, window=9).ema_indicator()
    df["ema_21"] = EMAIndicator(close=close, window=21).ema_indicator()
    df = df.dropna()

    if df.empty:
        return None

    latest = df.iloc[-1]
    payload = {
        "price": _as_float(latest["Close"]),
        "rsi": _as_float(latest["rsi"]),
        "ema_9": _as_float(latest["ema_9"]),
        "ema_21": _as_float(latest["ema_21"]),
    }
    _indicator_cache[ticker] = (datetime.now(timezone.utc), payload)
    return payload
