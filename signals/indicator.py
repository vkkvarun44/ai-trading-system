"""Indicator calculations for the strategy engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf
from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator, EMAIndicator, MACD
from ta.volatility import AverageTrueRange

from core.config import settings
from core.logger import get_logger
from signals.market_regime import detect_latest_regime

logger = get_logger(__name__)

_indicator_cache: dict[str, tuple[datetime, dict[str, float]]] = {}
_indicator_backoff_until: datetime | None = None


def _normalize_price_frame(data: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if isinstance(data.columns, pd.MultiIndex):
        try:
            return data.xs(ticker, axis=1, level=0)
        except KeyError:
            return pd.DataFrame()
    return data


def _as_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(dtype=float)

    values = frame[column]
    if isinstance(values, pd.DataFrame):
        values = values.iloc[:, 0]
    return pd.to_numeric(values, errors="coerce").dropna()


def _as_float(value: object) -> float:
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


def fetch_indicator_frame(ticker: str) -> pd.DataFrame:
    """Fetch OHLCV candles needed for signal-quality filters."""

    if _rate_limit_active():
        logger.info("Skipping indicator refresh for %s while Yahoo cooldown is active", ticker)
        return pd.DataFrame()

    frame = pd.DataFrame()
    for attempt in range(1, settings.yahoo_retry_count + 2):
        try:
            raw = yf.download(
                tickers=ticker,
                period="60d",
                interval="15m",
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=False,
                timeout=settings.yahoo_timeout_seconds,
            )
            frame = _normalize_price_frame(raw, ticker).dropna()
            if not frame.empty:
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

    if frame.empty or len(frame) < 220:
        return pd.DataFrame()

    normalized = frame.copy()
    for column in ("Open", "High", "Low", "Close", "Volume"):
        normalized[column] = _as_series(frame, column)
    normalized = normalized.dropna()
    if normalized.empty or len(normalized) < 220:
        return pd.DataFrame()
    return normalized


def get_indicators(ticker: str) -> dict[str, float] | None:
    """Fetch and calculate indicators for a ticker."""

    cached = _indicator_cache.get(ticker)
    if cached:
        cached_at, payload = cached
        if datetime.now(timezone.utc) - cached_at <= timedelta(seconds=settings.indicators_cache_seconds):
            return payload

    df = fetch_indicator_frame(ticker)
    if df.empty:
        return cached[1] if cached else None

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    df = df.copy()
    regime, regime_confidence, regime_row = detect_latest_regime(df)

    df["rsi"] = RSIIndicator(close=close, window=14).rsi()
    df["ema_9"] = EMAIndicator(close=close, window=9).ema_indicator()
    df["ema_21"] = EMAIndicator(close=close, window=21).ema_indicator()
    df["ema_50"] = EMAIndicator(close=close, window=50).ema_indicator()
    df["ema_200"] = EMAIndicator(close=close, window=200).ema_indicator()
    macd = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["atr"] = AverageTrueRange(high=high, low=low, close=close, window=14).average_true_range()
    df["adx"] = ADXIndicator(high=high, low=low, close=close, window=14).adx()
    df["avg_volume_20"] = volume.rolling(window=20).mean()
    df["volume_ratio"] = volume / df["avg_volume_20"]
    df = df.dropna()

    if df.empty:
        return cached[1] if cached else None

    latest = df.iloc[-1]
    payload = {
        "price": _as_float(latest["Close"]),
        "rsi": _as_float(latest["rsi"]),
        "ema_9": _as_float(latest["ema_9"]),
        "ema_21": _as_float(latest["ema_21"]),
        "ema_50": _as_float(latest["ema_50"]),
        "ema_200": _as_float(latest["ema_200"]),
        "macd": _as_float(latest["macd"]),
        "macd_signal": _as_float(latest["macd_signal"]),
        "atr": _as_float(latest["atr"]),
        "adx": _as_float(latest["adx"]),
        "volume_ratio": _as_float(latest["volume_ratio"]),
        "current_volume": _as_float(latest["Volume"]),
        "avg_volume_20": _as_float(latest["avg_volume_20"]),
        "regime": regime,
        "regime_confidence": float(regime_confidence),
    }
    if regime_row is not None:
        payload["ema_50_slope"] = _as_float(regime_row["ema_50_slope"])
        payload["ema_200_slope"] = _as_float(regime_row["ema_200_slope"])
        payload["volatility"] = _as_float(regime_row["volatility"])
        payload["trend_strength"] = _as_float(regime_row["trend_strength"])
    _indicator_cache[ticker] = (datetime.now(timezone.utc), payload)
    return payload
