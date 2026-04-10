"""Trade validation and risk controls for the execution pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from core.config import Settings
from db.models import SignalModel


@dataclass(slots=True)
class RiskDecision:
    approved: bool
    qty: int
    stop_loss: float
    target_price: float
    risk_amount: float
    reward_amount: float
    reason: str | None = None


def calculate_position_size(
    *,
    capital: float,
    entry_price: float,
    stop_loss: float,
    settings: Settings,
) -> tuple[int, float]:
    """Size a position from capital risk and stop-loss distance."""

    stop_distance = abs(entry_price - stop_loss)
    if stop_distance <= 0:
        return 0, 0.0

    risk_amount = capital * settings.max_risk_per_trade
    qty = int(risk_amount / stop_distance)
    qty = max(0, min(qty, settings.max_position_size))
    return qty, risk_amount


def apply_risk_management(
    *,
    signal: SignalModel,
    capital: float,
    settings: Settings,
) -> RiskDecision:
    """Derive ATR-based stop, target, and approved size."""

    if signal.atr <= 0:
        return RiskDecision(False, 0, 0.0, 0.0, 0.0, 0.0, "ATR is unavailable for sizing.")

    required_rr = signal.strategy_reward_ratio or settings.reward_ratio
    target_multiplier = settings.atr_stop_loss_multiplier * required_rr

    if signal.signal == "BUY":
        stop_loss = signal.price - (settings.atr_stop_loss_multiplier * signal.atr)
        target_price = signal.price + (target_multiplier * signal.atr)
    elif signal.signal == "SELL":
        stop_loss = signal.price + (settings.atr_stop_loss_multiplier * signal.atr)
        target_price = signal.price - (target_multiplier * signal.atr)
    else:
        return RiskDecision(False, 0, 0.0, 0.0, 0.0, 0.0, "Signal is not executable.")

    qty, risk_amount = calculate_position_size(
        capital=capital,
        entry_price=signal.price,
        stop_loss=stop_loss,
        settings=settings,
    )
    qty = int(qty * max(0.0, signal.position_size_multiplier))
    reward_amount = abs(target_price - signal.price)
    rr_ratio = reward_amount / abs(signal.price - stop_loss) if signal.price != stop_loss else 0.0
    if rr_ratio < required_rr:
        return RiskDecision(
            False,
            0,
            stop_loss,
            target_price,
            risk_amount,
            reward_amount,
            f"Risk-reward ratio {rr_ratio:.2f} is below required {required_rr:.2f}.",
        )
    if qty <= 0:
        return RiskDecision(
            False,
            0,
            stop_loss,
            target_price,
            risk_amount,
            reward_amount,
            "Position size computed to zero.",
        )
    return RiskDecision(True, qty, stop_loss, target_price, risk_amount, reward_amount)


def validate_trade(
    *,
    signal: SignalModel,
    current_trade_count: int,
    settings: Settings,
) -> str | None:
    """Check non-price trade constraints before execution."""

    if signal.signal not in {"BUY", "SELL"}:
        return "Signal is not actionable."
    if signal.regime_confidence and signal.regime_confidence < 0.6:
        return (
            f"Regime confidence too low for execution: {signal.regime} "
            f"{signal.regime_confidence:.2f} < 0.60."
        )
    if signal.strategy_direction == "BUY" and signal.signal != "BUY":
        return f"Regime {signal.regime} allows long trades only."
    if signal.strategy_direction == "SELL" and signal.signal != "SELL":
        return f"Regime {signal.regime} allows short trades only."
    return None


def daily_loss_limit_reached(
    *,
    starting_capital: float,
    current_equity: float,
    settings: Settings,
) -> bool:
    """Return True when the intraday kill switch should stop new entries."""

    if starting_capital <= 0:
        return False
    daily_loss = max(0.0, starting_capital - current_equity)
    return daily_loss >= (starting_capital * settings.daily_loss_limit_pct)


def get_session_trade_count(trades: list, *, timezone_name: str) -> int:
    """Return filled-trade count for the current market session date."""

    market_timezone = ZoneInfo(timezone_name)
    session_date = datetime.now(market_timezone).date()
    return sum(
        1
        for trade in trades
        if trade.status == "FILLED" and trade.timestamp.astimezone(market_timezone).date() == session_date
    )
