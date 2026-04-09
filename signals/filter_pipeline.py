"""Signal-quality filters and trade candidate selection."""

from __future__ import annotations

from datetime import datetime, timezone

from core.config import settings
from core.logger import get_logger
from db.models import MarketMover, SignalModel
from signals.indicator import get_indicators

logger = get_logger(__name__)


def filter_stocks(stocks: list[MarketMover]) -> tuple[list[SignalModel], list[SignalModel]]:
    """Apply layered filters before a stock becomes an executable signal."""

    accepted: list[SignalModel] = []
    rejected: list[SignalModel] = []

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

        candidate = build_candidate_signal(stock, indicators)
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

    signal = "HOLD"
    rejection_reason: str | None = None

    if volume_ratio < settings.min_volume_ratio:
        signal = "AVOID"
        rejection_reason = (
            f"Liquidity filter failed: volume ratio {volume_ratio:.2f} "
            f"< {settings.min_volume_ratio:.2f}."
        )
    elif atr < settings.min_atr:
        signal = "AVOID"
        rejection_reason = f"Volatility filter failed: ATR {atr:.2f} < {settings.min_atr:.2f}."
    elif adx < settings.min_adx:
        signal = "AVOID"
        rejection_reason = f"Market condition filter failed: ADX {adx:.2f} < {settings.min_adx:.2f}."
    elif price > ema_50 > ema_200:
        if rsi > settings.rsi_buy_threshold or macd > macd_signal:
            signal = "BUY"
        else:
            signal = "HOLD"
            rejection_reason = (
                f"Momentum filter failed for long setup: RSI {rsi:.2f}, "
                f"MACD {macd:.4f}, signal {macd_signal:.4f}."
            )
    elif price < ema_50 < ema_200:
        if rsi < settings.rsi_sell_threshold or macd < macd_signal:
            signal = "SELL"
        else:
            signal = "HOLD"
            rejection_reason = (
                f"Momentum filter failed for short setup: RSI {rsi:.2f}, "
                f"MACD {macd:.4f}, signal {macd_signal:.4f}."
            )
    else:
        signal = "AVOID"
        rejection_reason = "Trend filter failed: price is not aligned with EMA50 and EMA200."

    stop_loss, target_price = _risk_levels(price=price, atr=atr, signal=signal)

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
        stop_loss=stop_loss,
        target_price=target_price,
        rejection_reason=rejection_reason,
        change_pct=stock.change_pct,
        generated_at=datetime.now(timezone.utc),
    )


def _risk_levels(*, price: float, atr: float, signal: str) -> tuple[float, float]:
    if signal == "BUY":
        return (
            price - (settings.atr_stop_loss_multiplier * atr),
            price + (settings.atr_target_multiplier * atr),
        )
    if signal == "SELL":
        return (
            price + (settings.atr_stop_loss_multiplier * atr),
            price - (settings.atr_target_multiplier * atr),
        )
    return 0.0, 0.0


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
