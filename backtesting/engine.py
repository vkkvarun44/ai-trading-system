"""Intraday backtesting engine using the live regime and strategy helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from signals.market_regime import (
    analyze_performance,
    calculate_atr_levels,
    evaluate_strategy_signal,
    predict_with_confidence,
    prepare_regime_frame,
)


@dataclass(slots=True)
class BacktestPosition:
    side: str
    entry_price: float
    qty: int
    stop_loss: float
    target_price: float
    regime: str
    confidence: float
    opened_at: Any


def _value(row: pd.Series, *names: str) -> float:
    for name in names:
        if name in row:
            return float(row[name])
    raise KeyError(f"Missing required column. Expected one of: {', '.join(names)}")


def _session_date(index_value: Any) -> date | None:
    if hasattr(index_value, "date"):
        return index_value.date()
    return None


def _position_size(
    *,
    balance: float,
    entry_price: float,
    stop_loss: float,
    risk_per_trade: float,
    position_size_multiplier: float,
) -> int:
    stop_distance = abs(entry_price - stop_loss)
    if stop_distance <= 0:
        return 0
    risk_amount = balance * risk_per_trade
    return max(0, int((risk_amount / stop_distance) * position_size_multiplier))


def _exit_price(position: BacktestPosition, row: pd.Series) -> tuple[float | None, str | None]:
    high = _value(row, "High", "high")
    low = _value(row, "Low", "low")

    if position.side == "BUY":
        if low <= position.stop_loss:
            return position.stop_loss, "STOP_LOSS"
        if high >= position.target_price:
            return position.target_price, "TARGET"
    else:
        if high >= position.stop_loss:
            return position.stop_loss, "STOP_LOSS"
        if low <= position.target_price:
            return position.target_price, "TARGET"
    return None, None


def _close_position(
    *,
    position: BacktestPosition,
    exit_price: float,
    exited_at: Any,
    reason: str,
) -> dict[str, Any]:
    pnl = (
        (exit_price - position.entry_price) * position.qty
        if position.side == "BUY"
        else (position.entry_price - exit_price) * position.qty
    )
    return {
        "stock": "BACKTEST_SYMBOL",
        "side": position.side,
        "entry_price": position.entry_price,
        "exit_price": exit_price,
        "qty": position.qty,
        "regime": position.regime,
        "confidence": position.confidence,
        "profit": pnl,
        "entry_time": position.opened_at,
        "exit_time": exited_at,
        "exit_reason": reason,
    }


def run_backtest(
    df: pd.DataFrame,
    model,
    *,
    initial_capital: float = 100000.0,
    risk_per_trade: float = 0.01,
    daily_loss_limit_pct: float = 0.03,
    max_trades_per_day: int | None = None,
    stop_multiplier: float = 1.5,
) -> dict[str, Any]:
    """Run a realistic intraday backtest with shared live-trading logic."""

    data = prepare_regime_frame(df)
    if data.empty:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "total_profit": 0.0,
            "max_drawdown": 0.0,
            "profit_factor": 0.0,
            "ending_balance": initial_capital,
            "trades": [],
            "performance": analyze_performance([]),
        }

    balance = float(initial_capital)
    peak_balance = balance
    max_drawdown = 0.0
    daily_start_balance = balance
    daily_trades = 0
    active_session = _session_date(data.index[0])
    position: BacktestPosition | None = None
    trades: list[dict[str, Any]] = []
    equity_curve: list[float] = [balance]
    previous_close: float | None = None
    previous_index: Any = None

    for index_value, row in data.iterrows():
        session = _session_date(index_value)
        close = _value(row, "Close", "close")

        if active_session is not None and session != active_session:
            if position is not None:
                trade = _close_position(
                    position=position,
                    exit_price=previous_close if previous_close is not None else close,
                    exited_at=previous_index if previous_index is not None else index_value,
                    reason="EOD_SQUARE_OFF",
                )
                trades.append(trade)
                balance += trade["profit"]
                position = None
            active_session = session
            daily_start_balance = balance
            daily_trades = 0

        if position is not None:
            exit_price, exit_reason = _exit_price(position, row)
            if exit_price is not None and exit_reason is not None:
                trade = _close_position(
                    position=position,
                    exit_price=exit_price,
                    exited_at=index_value,
                    reason=exit_reason,
                )
                trades.append(trade)
                balance += trade["profit"]
                position = None

        peak_balance = max(peak_balance, balance)
        drawdown = (peak_balance - balance) / peak_balance if peak_balance > 0 else 0.0
        max_drawdown = max(max_drawdown, drawdown)
        equity_curve.append(balance)

        daily_loss = max(0.0, daily_start_balance - balance)
        daily_loss_limit = daily_start_balance * daily_loss_limit_pct
        trade_limit_reached = max_trades_per_day is not None and daily_trades >= max_trades_per_day
        if daily_loss >= daily_loss_limit or trade_limit_reached or position is not None:
            previous_close = close
            previous_index = index_value
            continue

        regime, confidence = predict_with_confidence(model, row)
        decision = evaluate_strategy_signal(row=row, regime=regime, confidence=confidence)
        if decision.signal not in {"BUY", "SELL"}:
            previous_close = close
            previous_index = index_value
            continue

        atr = _value(row, "atr")
        stop_loss, target_price = calculate_atr_levels(
            price=close,
            atr=atr,
            signal=decision.signal,
            params=decision.params,
            stop_multiplier=stop_multiplier,
        )
        qty = _position_size(
            balance=balance,
            entry_price=close,
            stop_loss=stop_loss,
            risk_per_trade=risk_per_trade,
            position_size_multiplier=decision.params.position_size_multiplier,
        )
        if qty <= 0:
            previous_close = close
            previous_index = index_value
            continue

        position = BacktestPosition(
            side=decision.signal,
            entry_price=close,
            qty=qty,
            stop_loss=stop_loss,
            target_price=target_price,
            regime=regime,
            confidence=confidence,
            opened_at=index_value,
        )
        daily_trades += 1
        previous_close = close
        previous_index = index_value

    if position is not None:
        last_row = data.iloc[-1]
        trade = _close_position(
            position=position,
            exit_price=_value(last_row, "Close", "close"),
            exited_at=data.index[-1],
            reason="FINAL_SQUARE_OFF",
        )
        trades.append(trade)
        balance += trade["profit"]

    profits = [float(trade["profit"]) for trade in trades]
    gross_profit = sum(profit for profit in profits if profit > 0)
    gross_loss = abs(sum(profit for profit in profits if profit < 0))
    total_trades = len(trades)
    wins = sum(1 for profit in profits if profit > 0)

    return {
        "total_trades": total_trades,
        "win_rate": wins / total_trades if total_trades else 0.0,
        "total_profit": balance - initial_capital,
        "max_drawdown": max_drawdown,
        "profit_factor": gross_profit / gross_loss if gross_loss else float(gross_profit > 0),
        "ending_balance": balance,
        "equity_curve": equity_curve,
        "trades": trades,
        "performance": analyze_performance(trades),
    }
