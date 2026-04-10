"""Signal-quality filters and trade candidate selection."""

from __future__ import annotations

from datetime import datetime, timezone

from core.config import settings
from core.logger import get_logger
from db.models import MarketMover, SignalModel
from signals.indicator import get_indicators
from signals.market_regime import (
    REGIME_SIDEWAYS,
    calculate_atr_levels,
    evaluate_strategy_signal,
    rank_stocks,
)

logger = get_logger(__name__)


def filter_stocks(
    stocks: list[MarketMover],
    model=None,
) -> tuple[list[SignalModel], list[SignalModel]]:
    """Apply layered filters before a stock becomes an executable signal."""

    accepted: list[SignalModel] = []
    rejected: list[SignalModel] = []
    indicator_rows: dict[str, dict[str, float]] = {}
    stock_lookup = {stock.ticker: stock for stock in stocks}

    for stock in stocks:
        indicators = get_indicators(stock.ticker)
        if not indicators:
            candidate = _build_rejected_signal(
                stock,
                "Indicator fetch failed or returned insufficient history.",
            )
            rejected.append(candidate)
            logger.info("Rejected %s: %s", stock.ticker, candidate.rejection_reason)
            continue

        indicator_rows[stock.ticker] = indicators

    ranked_tickers = list(indicator_rows)
    if model is not None and indicator_rows:
        ranked_tickers = [item["stock"] for item in rank_stocks(indicator_rows, model)]

    for ticker in ranked_tickers:
        stock = stock_lookup[ticker]
        indicators = indicator_rows[ticker]
        candidate = build_candidate_signal(stock, indicators)
        logger.info(
            "Detected regime for %s: %s (confidence %.2f)",
            stock.ticker,
            candidate.regime,
            candidate.regime_confidence,
        )
        if candidate.signal in {"BUY", "SELL"}:
            accepted.append(candidate)
        else:
            rejected.append(candidate)
            logger.info("Rejected %s: %s", stock.ticker, candidate.rejection_reason)

    return accepted, rejected


def build_candidate_signal(stock: MarketMover, indicators: dict[str, float]) -> SignalModel:
    """Build one signal after applying trend, momentum, and quality filters."""

    price = indicators["price"]
    atr = indicators["atr"]
    ema_50 = indicators["ema_50"]
    ema_200 = indicators["ema_200"]
    rsi = indicators["rsi"]
    macd = indicators["macd"]
    macd_signal = indicators["macd_signal"]
    adx = indicators["adx"]
    volume_ratio = indicators["volume_ratio"]
    regime = str(indicators.get("regime", REGIME_SIDEWAYS))
    regime_confidence = float(indicators.get("regime_confidence", 0.0))
    trend_strength = float(indicators.get("trend_strength", ema_50 - ema_200))
    strategy_decision = evaluate_strategy_signal(
        row={
            **indicators,
            "price": price,
            "trend_strength": trend_strength,
        },
        regime=regime,
        confidence=regime_confidence,
    )
    strategy_params = strategy_decision.params

    signal = strategy_decision.signal
    rejection_reason = strategy_decision.reason
    if volume_ratio < settings.min_volume_ratio:
        signal = "AVOID"
        rejection_reason = (
            f"Liquidity filter failed: volume ratio {volume_ratio:.2f} "
            f"< {settings.min_volume_ratio:.2f}."
        )
    elif atr < settings.min_atr:
        signal = "AVOID"
        rejection_reason = f"Volatility filter failed: ATR {atr:.2f} < {settings.min_atr:.2f}."
    elif adx < max(settings.min_adx, strategy_params.min_adx) and regime != REGIME_SIDEWAYS:
        signal = "AVOID"
        rejection_reason = (
            f"Market condition filter failed for {regime}: ADX {adx:.2f} "
            f"< {max(settings.min_adx, strategy_params.min_adx):.2f}."
        )

    stop_loss, target_price = calculate_atr_levels(
        price=price,
        atr=atr,
        signal=signal,
        params=strategy_params,
        stop_multiplier=settings.atr_stop_loss_multiplier,
    )

    return SignalModel(
        ticker=stock.ticker,
        signal=signal,
        price=price,
        rsi=rsi,
        ema_9=indicators["ema_9"],
        ema_21=indicators["ema_21"],
        ema_50=ema_50,
        ema_200=ema_200,
        macd=macd,
        macd_signal=macd_signal,
        atr=atr,
        adx=adx,
        volume_ratio=volume_ratio,
        trend_strength=trend_strength,
        regime=regime,
        regime_confidence=regime_confidence,
        strategy_direction="both"
        if len(strategy_params.allowed_directions) > 1
        else strategy_params.allowed_directions[0],
        strategy_reward_ratio=strategy_params.reward_ratio,
        position_size_multiplier=strategy_params.position_size_multiplier,
        stop_loss=stop_loss,
        target_price=target_price,
        rejection_reason=rejection_reason,
        change_pct=stock.change_pct,
        generated_at=datetime.now(timezone.utc),
    )


def _build_rejected_signal(stock: MarketMover, reason: str) -> SignalModel:
    return SignalModel(
        ticker=stock.ticker,
        signal="AVOID",
        price=stock.price,
        rsi=0.0,
        ema_9=0.0,
        ema_21=0.0,
        rejection_reason=reason,
        change_pct=stock.change_pct,
        generated_at=datetime.now(timezone.utc),
    )
