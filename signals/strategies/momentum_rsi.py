"""Momentum + RSI + EMA strategy."""

from __future__ import annotations


def momentum_rsi_strategy(indicators: dict[str, float], change_pct: float) -> str:
    """Return a trading signal from the current indicator state."""

    rsi = indicators["rsi"]
    ema_9 = indicators["ema_9"]
    ema_21 = indicators["ema_21"]

    if change_pct > 1.5 and rsi < 70 and ema_9 > ema_21:
        return "BUY"

    if change_pct < -1.5 and rsi > 30 and ema_9 < ema_21:
        return "SELL"

    if rsi > 75:
        return "AVOID"

    return "HOLD"
