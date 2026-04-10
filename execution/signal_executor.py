"""Signal execution pipeline with cooldown, sizing, and risk rules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.config import Settings
from core.logger import get_logger
from db.models import SignalModel, TradeModel
from execution.paper_trader import PaperTradingEngine, Position
from execution.risk_management import (
    apply_risk_management,
    daily_loss_limit_reached,
    get_session_trade_count,
    validate_trade,
)
from state.store import TradingState

logger = get_logger(__name__)


class SignalExecutor:
    """Translate filtered signals into simulated broker orders."""

    def __init__(self, engine: PaperTradingEngine, state: TradingState, settings: Settings) -> None:
        self.engine = engine
        self.state = state
        self.settings = settings

    def execute_trade(self, signal: SignalModel, *, force: bool = False) -> TradeModel | None:
        """Execute one validated signal."""

        position = self.engine.positions.get(signal.ticker)
        action = self._normalize_signal(signal.signal)
        if action is None:
            return None

        if not force and self._in_cooldown(signal.ticker):
            return self._build_skipped_trade(signal, action, "Ticker is cooling down from a recent trade.")

        if not force and self._is_duplicate(signal):
            return self._build_skipped_trade(
                signal,
                action,
                "Duplicate trade avoided for existing position state.",
            )

        if not force:
            from app.dependencies import market_profile_manager

            session_trades = get_session_trade_count(
                self.state.get_trades(),
                timezone_name=market_profile_manager.get_active_profile().timezone,
            )
            portfolio = self.engine.get_portfolio({signal.ticker: signal.price})
            if daily_loss_limit_reached(
                starting_capital=self.engine.initial_capital,
                current_equity=portfolio.total_value,
                settings=self.settings,
            ):
                return self._build_skipped_trade(
                    signal,
                    action,
                    f"Daily loss kill switch triggered at {self.settings.daily_loss_limit_pct:.2%}.",
                )
            reason = validate_trade(
                signal=signal,
                current_trade_count=session_trades,
                settings=self.settings,
            )
            if reason:
                return self._build_skipped_trade(signal, action, reason)

        qty = self._resolve_order_qty(signal=signal, position=position, force=force)
        if qty <= 0:
            return self._build_skipped_trade(signal, action, "Position size resolved to zero.")

        order = self.engine.place_order(
            ticker=signal.ticker,
            price=signal.price,
            signal=action,
            qty=qty,
            stop_loss=signal.stop_loss or None,
            target_price=signal.target_price or None,
        )
        if order.status == "FILLED":
            self.state.set_cooldown(signal.ticker, order.timestamp)
        return order

    def execute_signals(
        self,
        signals: list[SignalModel],
        *,
        force: bool = False,
    ) -> list[TradeModel]:
        """Execute a batch of signals."""

        orders: list[TradeModel] = []
        for signal in signals:
            order = self.execute_trade(signal, force=force)
            if order:
                orders.append(order)
        return orders

    def generate_exit_signals(self, current_prices: dict[str, float]) -> list[SignalModel]:
        """Create stop-loss/take-profit exit signals for open positions."""

        exit_signals: list[SignalModel] = []
        now = datetime.now(timezone.utc)

        for ticker, position in list(self.engine.positions.items()):
            if position.qty <= 0:
                continue

            price = current_prices.get(ticker)
            if price is None:
                continue

            stop_loss, target_price = self._position_risk_levels(position)
            if position.side == "LONG" and (price <= stop_loss or price >= target_price):
                exit_signals.append(
                    SignalModel(
                        ticker=ticker,
                        signal="SELL",
                        price=price,
                        rsi=0.0,
                        ema_9=0.0,
                        ema_21=0.0,
                        atr=max(abs(position.avg_price - stop_loss), 0.0),
                        stop_loss=stop_loss,
                        target_price=target_price,
                        change_pct=0.0,
                        generated_at=now,
                    )
                )
            elif position.side == "SHORT" and (price >= stop_loss or price <= target_price):
                exit_signals.append(
                    SignalModel(
                        ticker=ticker,
                        signal="BUY",
                        price=price,
                        rsi=0.0,
                        ema_9=0.0,
                        ema_21=0.0,
                        atr=max(abs(stop_loss - position.avg_price), 0.0),
                        stop_loss=stop_loss,
                        target_price=target_price,
                        change_pct=0.0,
                        generated_at=now,
                    )
                )

        return exit_signals

    def close_positions_for_end_of_day(self, current_prices: dict[str, float]) -> list[TradeModel]:
        """Flatten all positions before the closing bell."""

        eod_signals: list[SignalModel] = []
        now = datetime.now(timezone.utc)
        for ticker, position in list(self.engine.positions.items()):
            price = current_prices.get(ticker, position.avg_price)
            signal = "SELL" if position.side == "LONG" else "BUY"
            eod_signals.append(
                SignalModel(
                    ticker=ticker,
                    signal=signal,
                    price=price,
                    rsi=0.0,
                    ema_9=0.0,
                    ema_21=0.0,
                    atr=0.0,
                    stop_loss=0.0,
                    target_price=0.0,
                    change_pct=0.0,
                    generated_at=now,
                    rejection_reason="End-of-day square off.",
                )
            )
        return self.execute_signals(eod_signals, force=True)

    def _normalize_signal(self, signal: str) -> str | None:
        if signal == "SHORT":
            return "SELL"
        if signal == "COVER":
            return "BUY"
        if signal in {"BUY", "SELL"}:
            return signal
        return None

    def _resolve_order_qty(
        self,
        *,
        signal: SignalModel,
        position: Position | None,
        force: bool,
    ) -> int:
        if force and position:
            if signal.signal == "SELL" and position.side == "LONG":
                return position.qty
            if signal.signal == "BUY" and position.side == "SHORT":
                return position.qty

        decision = apply_risk_management(
            signal=signal,
            capital=self.engine.cash,
            settings=self.settings,
        )
        if not decision.approved:
            logger.info("Rejected %s: %s", signal.ticker, decision.reason)
            return 0
        return decision.qty

    def _position_risk_levels(self, position: Position) -> tuple[float, float]:
        atr = position.stop_loss if position.stop_loss is not None else 0.0
        if atr > 0:
            stop_distance = abs(position.avg_price - atr)
            target_distance = stop_distance * self.settings.reward_ratio
        else:
            stop_distance = max(position.avg_price * self.settings.stop_loss_pct, 0.01)
            target_distance = max(position.avg_price * self.settings.take_profit_pct, stop_distance)

        if position.side == "LONG":
            return position.avg_price - stop_distance, position.avg_price + target_distance
        return position.avg_price + stop_distance, position.avg_price - target_distance

    def _build_skipped_trade(self, signal: SignalModel, action: str, reason: str) -> TradeModel:
        logger.info("Rejected %s: %s", signal.ticker, reason)
        return self.engine._build_trade(
            ticker=signal.ticker,
            side=action,
            qty=0,
            price=signal.price,
            status="SKIPPED",
            signal=signal.signal,
            reason=reason,
            realized_pnl=0.0,
            timestamp=datetime.now(timezone.utc),
        )

    def _in_cooldown(self, ticker: str) -> bool:
        cooldown_started = self.state.get_cooldown(ticker)
        if not cooldown_started:
            return False
        return datetime.now(timezone.utc) - cooldown_started < timedelta(
            seconds=self.settings.signal_cooldown_seconds
        )

    def _is_duplicate(self, signal: SignalModel) -> bool:
        portfolio = self.engine.get_portfolio({signal.ticker: signal.price})
        position = next((item for item in portfolio.positions if item.ticker == signal.ticker), None)
        if not position:
            return False
        return (signal.signal == "BUY" and position.side == "LONG") or (
            signal.signal == "SELL" and position.side == "SHORT"
        )
