"""Market data helpers built on Yahoo Finance."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

from core.config import settings
from core.logger import get_logger
from db.models import AutoWatchlistCandidateModel, MarketMover
from signals.market_regime import (
    FEATURE_COLUMNS,
    REGIME_SIDEWAYS,
    add_indicators,
    create_features,
    label_market,
    predict_with_confidence,
    train_model,
)

logger = get_logger(__name__)

_price_cache: dict[str, tuple[datetime, float]] = {}
_top_movers_cache: dict[str, tuple[datetime, dict[str, list[MarketMover]]]] = {}
_ranked_candidates_cache: dict[str, tuple[datetime, list[AutoWatchlistCandidateModel]]] = {}
_rate_limited_until: datetime | None = None

NO_TRADE_REGIMES = {REGIME_SIDEWAYS, "LOW_VOLATILITY"}


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
    _ranked_candidates_cache.clear()


def _prepare_prebreakout_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Build indicator and feature columns needed for pre-breakout ranking."""

    enriched = create_features(add_indicators(frame))
    enriched["atr_mean_20"] = enriched["atr"].rolling(window=20).mean()
    enriched["volatility_expansion"] = enriched["atr"] / enriched["atr_mean_20"]
    return enriched.dropna(subset=FEATURE_COLUMNS + ["volatility_expansion"])


def _train_regime_model_from_frames(frames: dict[str, pd.DataFrame]):
    """Train a transient regime model from the current watchlist universe."""

    training_frames: list[pd.DataFrame] = []
    for ticker, frame in frames.items():
        try:
            prepared = label_market(_prepare_prebreakout_frame(frame))
            if not prepared.empty:
                training_frames.append(prepared)
        except Exception as exc:
            logger.info("Skipping %s for transient regime training: %s", ticker, exc)

    if not training_frames:
        logger.info("No regime training data available for pre-breakout ranking.")
        return None

    try:
        return train_model(pd.concat(training_frames, axis=0).sort_index())
    except Exception as exc:
        logger.info("Could not train transient regime model for pre-breakout ranking: %s", exc)
        return None


def _normalize_positive(value: float, cap: float) -> float:
    if cap <= 0:
        return 0.0
    return max(0.0, min(value / cap, 1.0))


def _score_prebreakout_candidate(
    *,
    ticker: str,
    frame: pd.DataFrame,
    model,
    min_price: float,
    min_avg_volume: float,
) -> AutoWatchlistCandidateModel | None:
    try:
        if frame.empty or len(frame) < 220:
            logger.info("Rejected %s: insufficient history for EMA200/ATR ranking.", ticker)
            return None

        prepared = _prepare_prebreakout_frame(frame)
        if prepared.empty:
            logger.info("Rejected %s: indicator feature frame is empty.", ticker)
            return None

        latest = prepared.iloc[-1]
        price = float(latest["Close"])
        avg_volume = float(prepared["Volume"].tail(20).mean())
        current_volume = float(latest["Volume"])
        trend_strength = float(latest["trend_strength"])
        volume_ratio = float(latest["volume_ratio"])
        volatility_expansion = float(latest["volatility_expansion"])

        if price < min_price:
            logger.info("Rejected %s: price %.2f below minimum %.2f.", ticker, price, min_price)
            return None
        if avg_volume < min_avg_volume:
            logger.info(
                "Rejected %s: average volume %.2f below minimum %.2f.",
                ticker,
                avg_volume,
                min_avg_volume,
            )
            return None
        if trend_strength <= 0:
            logger.info("Rejected %s: trend_strength %.4f is not positive.", ticker, trend_strength)
            return None
        if volume_ratio <= 1.5:
            logger.info("Rejected %s: volume_ratio %.2f <= 1.50.", ticker, volume_ratio)
            return None
        if volatility_expansion <= 1.2:
            logger.info(
                "Rejected %s: volatility_expansion %.2f <= 1.20.",
                ticker,
                volatility_expansion,
            )
            return None
        if model is None:
            logger.info("Rejected %s: regime model unavailable for AI confidence filter.", ticker)
            return None

        regime, confidence = predict_with_confidence(model, latest)
        logger.info("Detected regime for %s: %s (confidence %.2f)", ticker, regime, confidence)
        if confidence < 0.6:
            logger.info("Rejected %s: confidence %.2f < 0.60.", ticker, confidence)
            return None
        if regime in NO_TRADE_REGIMES:
            logger.info("Rejected %s: no-trade regime %s.", ticker, regime)
            return None

        prev_close = float(prepared["Close"].iloc[-2])
        change_pct = ((price - prev_close) / prev_close) * 100 if prev_close else 0.0
        trend_score = _normalize_positive(trend_strength / price, 0.10)
        volume_score = _normalize_positive(volume_ratio, 3.0)
        volatility_score = _normalize_positive(volatility_expansion, 2.0)
        score = (
            (trend_score * 0.25)
            + (volume_score * 0.25)
            + (volatility_score * 0.2)
            + (confidence * 0.3)
        )
        logger.info(
            "Ranked %s: score %.4f, regime %s, confidence %.2f, trend %.4f, volume_ratio %.2f, volatility_expansion %.2f.",
            ticker,
            score,
            regime,
            confidence,
            trend_strength,
            volume_ratio,
            volatility_expansion,
        )

        return AutoWatchlistCandidateModel(
            ticker=ticker,
            price=round(price, 2),
            change_pct=round(change_pct, 2),
            avg_volume=round(avg_volume, 2),
            score=round(score, 4),
            trend_strength=round(trend_strength, 4),
            volume_ratio=round(volume_ratio, 4),
            volatility_expansion=round(volatility_expansion, 4),
            regime=regime,
            confidence=round(confidence, 4),
        )
    except Exception as exc:
        logger.warning("Could not rank pre-breakout candidate %s: %s", ticker, exc)
        return None


def _overall_market_allows_trading(
    *,
    frames: dict[str, pd.DataFrame],
    model,
) -> bool:
    """Block entries when the broad candidate universe is sideways or low volatility."""

    if model is None:
        logger.info("No-trade zone active: regime model unavailable.")
        return False

    latest_rows: list[pd.Series] = []
    for ticker, frame in frames.items():
        try:
            prepared = _prepare_prebreakout_frame(frame)
            if not prepared.empty:
                latest_rows.append(prepared.iloc[-1][FEATURE_COLUMNS])
        except Exception as exc:
            logger.info("Skipping %s from overall regime check: %s", ticker, exc)

    if not latest_rows:
        logger.info("No-trade zone active: no usable market features.")
        return False

    market_row = pd.DataFrame(latest_rows).mean(numeric_only=True)
    regime, confidence = predict_with_confidence(model, market_row)
    logger.info("Overall market regime: %s (confidence %.2f)", regime, confidence)
    if regime in NO_TRADE_REGIMES:
        logger.info("No-trade zone active: overall market regime is %s.", regime)
        return False
    return True


def rank_stocks(
    candidates: list[str] | dict[str, pd.DataFrame],
    model=None,
    *,
    top_n: int | None = 3,
    min_price: float | None = None,
    min_avg_volume: float | None = None,
) -> list[AutoWatchlistCandidateModel]:
    """Rank pre-breakout candidates using AI regime confidence and quality filters."""

    if not candidates:
        return []

    if isinstance(candidates, dict):
        frames = candidates
        tickers = list(candidates)
    else:
        tickers = list(dict.fromkeys(candidates))
        frames = _download_many_tickers(tickers, period="1y", interval="1d")

    resolved_min_price = min_price if min_price is not None else settings.auto_watchlist_min_price
    resolved_min_avg_volume = (
        min_avg_volume if min_avg_volume is not None else settings.auto_watchlist_min_avg_volume
    )
    cache_key = (
        f"rank:{','.join(sorted(tickers))}:{top_n if top_n is not None else 'all'}:"
        f"{resolved_min_price}:{resolved_min_avg_volume}:{id(model) if model is not None else 'auto'}"
    )
    cached = _ranked_candidates_cache.get(cache_key)
    if cached:
        cached_at, payload = cached
        if datetime.now(timezone.utc) - cached_at <= timedelta(seconds=settings.top_movers_cache_seconds):
            return payload

    regime_model = model or _train_regime_model_from_frames(frames)
    if not _overall_market_allows_trading(frames=frames, model=regime_model):
        _ranked_candidates_cache[cache_key] = (datetime.now(timezone.utc), [])
        return []

    ranked = [
        candidate
        for ticker, frame in frames.items()
        if (
            candidate := _score_prebreakout_candidate(
                ticker=ticker,
                frame=frame,
                model=regime_model,
                min_price=resolved_min_price,
                min_avg_volume=resolved_min_avg_volume,
            )
        )
    ]
    ranked = sorted(ranked, key=lambda item: item.score, reverse=True)
    payload = ranked[:top_n] if top_n is not None else ranked
    _ranked_candidates_cache[cache_key] = (datetime.now(timezone.utc), payload)
    return payload


def analyze_watchlist_candidates(
    tickers: list[str],
    *,
    min_price: float,
    min_avg_volume: float,
    model=None,
) -> list[AutoWatchlistCandidateModel]:
    """Rank a broader market universe into pre-breakout watchlist candidates."""

    return rank_stocks(
        tickers,
        model=model,
        top_n=None,
        min_price=min_price,
        min_avg_volume=min_avg_volume,
    )


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
