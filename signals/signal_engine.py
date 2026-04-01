"""Signal generation pipeline."""

from __future__ import annotations

from datetime import datetime, timezone

from db.models import MarketMover, SignalModel
from signals.indicator import get_indicators
from signals.strategies.momentum_rsi import momentum_rsi_strategy


def generate_signals(stocks: list[MarketMover]) -> list[SignalModel]:
    """Generate strategy signals for the supplied market movers."""

    results: list[SignalModel] = []
    generated_at = datetime.now(timezone.utc)

    for stock in stocks:
        indicators = get_indicators(stock.ticker)
        if not indicators:
            continue

        signal = momentum_rsi_strategy(indicators, stock.change_pct)
        results.append(
            SignalModel(
                ticker=stock.ticker,
                signal=signal,
                price=indicators["price"],
                rsi=indicators["rsi"],
                ema_9=indicators["ema_9"],
                ema_21=indicators["ema_21"],
                change_pct=stock.change_pct,
                generated_at=generated_at,
            )
        )

    return results
