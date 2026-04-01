"""Signal execution pipeline with cooldown, sizing, and risk rules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.config import Settings
from core.logger import get_logger
from db.models import SignalModel, TradeModel
from execution.paper_trader import PaperTradingEngine
from state.store import TradingState

logger = get_logger(__name__)


class SignalExecutor:
    """Translate strategy signals into simulated broker orders."""

    def __init__(self, engine: PaperTradingEngine, state: TradingState, settings: Settings) -> None:
        self.engine = engine
        self.state = state
        self.settings = settings

    def execute_signals(
        self,
        signals: list[SignalModel],
        *,
        force: bool = False,
    ) -> list[TradeModel]:
        """Execute BUY and SELL signals while preventing duplicates."""

        orders: list[TradeModel] = []

        for signal in signals:
            if signal.signal not in {"BUY", "SELL"}:
                continue

            if not force and self._in_cooldown(signal.ticker):
                orders.append(
                    self.engine._build_trade(
                        ticker=signal.ticker,
                        side=signal.signal,
                        qty=0,
                        price=signal.price,
                        status="SKIPPED",
                        signal=signal.signal,
                        reason="Ticker is cooling down from a recent trade.",
                        realized_pnl=0.0,
                        timestamp=datetime.now(timezone.utc),
                    )
                )
                continue

            if not force and self._is_duplicate(signal):
                orders.append(
                    self.engine._build_trade(
                        ticker=signal.ticker,
                        side=signal.signal,
                        qty=0,
                        price=signal.price,
                        status="SKIPPED",
                        signal=signal.signal,
                        reason="Duplicate trade avoided for existing position state.",
                        realized_pnl=0.0,
                        timestamp=datetime.now(timezone.utc),
                    )
                )
                continue

            qty = self._position_size(signal.price)
            order = self.engine.place_order(
                ticker=signal.ticker,
                price=signal.price,
                signal=signal.signal,
                qty=qty,
            )
            orders.append(order)

            if order.status == "FILLED":
                self.state.set_cooldown(signal.ticker, order.timestamp)

        return orders

    def generate_exit_signals(self, current_prices: dict[str, float]) -> list[SignalModel]:
        """Create stop-loss/take-profit exit signals for open positions."""

        exit_signals: list[SignalModel] = []
        positions = self.engine.get_portfolio(current_prices).positions
        now = datetime.now(timezone.utc)

        for position in positions:
            if position.qty <= 0:
                continue

            if position.side == "LONG":
                stop_loss_price = position.avg_price * (1 - self.settings.stop_loss_pct)
                take_profit_price = position.avg_price * (1 + self.settings.take_profit_pct)

                if position.market_price <= stop_loss_price:
                    exit_signals.append(
                        SignalModel(
                            ticker=position.ticker,
                            signal="SELL",
                            price=position.market_price,
                            rsi=0.0,
                            ema_9=0.0,
                            ema_21=0.0,
                            change_pct=0.0,
                            generated_at=now,
                        )
                    )
                elif position.market_price >= take_profit_price:
                    exit_signals.append(
                        SignalModel(
                            ticker=position.ticker,
                            signal="SELL",
                            price=position.market_price,
                            rsi=0.0,
                            ema_9=0.0,
                            ema_21=0.0,
                            change_pct=0.0,
                            generated_at=now,
                        )
                    )
            else:
                stop_loss_price = position.avg_price * (1 + self.settings.stop_loss_pct)
                take_profit_price = position.avg_price * (1 - self.settings.take_profit_pct)

                if position.market_price >= stop_loss_price:
                    exit_signals.append(
                        SignalModel(
                            ticker=position.ticker,
                            signal="BUY",
                            price=position.market_price,
                            rsi=0.0,
                            ema_9=0.0,
                            ema_21=0.0,
                            change_pct=0.0,
                            generated_at=now,
                        )
                    )
                elif position.market_price <= take_profit_price:
                    exit_signals.append(
                        SignalModel(
                            ticker=position.ticker,
                            signal="BUY",
                            price=position.market_price,
                            rsi=0.0,
                            ema_9=0.0,
                            ema_21=0.0,
                            change_pct=0.0,
                            generated_at=now,
                        )
                    )

        return exit_signals

    def _position_size(self, price: float) -> int:
        if self.settings.fixed_position_size > 0:
            return self.settings.fixed_position_size

        budget = self.engine.cash * self.settings.position_size_pct
        return max(int(budget // price), 1)

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
