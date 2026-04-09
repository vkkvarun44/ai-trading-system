"""Paper trading engine for simulated order execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from threading import RLock
from uuid import uuid4

from core.logger import get_logger
from db.models import (
    DailyInvestmentRecordModel,
    PnLResponseModel,
    PnLSnapshotModel,
    PortfolioModel,
    PositionModel,
    TradeModel,
)
from db.persistence import PersistenceManager
from state.store import TradingState

logger = get_logger(__name__)


@dataclass
class Position:
    ticker: str
    qty: int
    avg_price: float
    side: str = "LONG"
    stop_loss: float | None = None
    target_price: float | None = None
    realized_pnl: float = 0.0
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class PaperTradingEngine:
    """A small stateful broker simulator for paper trading."""

    def __init__(
        self,
        initial_capital: float,
        state: TradingState,
        persistence: PersistenceManager | None = None,
    ) -> None:
        self.initial_capital = float(initial_capital)
        self.cash = float(initial_capital)
        self.active_market = "US"
        self.positions: dict[str, Position] = {}
        self.state = state
        self.persistence = persistence
        self.lock = RLock()
        self.updated_at = datetime.now(timezone.utc)
        self.session_started_at = self.updated_at
        self.last_settlement_date: date | None = None

    def place_order(
        self,
        ticker: str,
        price: float,
        signal: str,
        qty: int,
        *,
        stop_loss: float | None = None,
        target_price: float | None = None,
    ) -> TradeModel:
        """Simulate a BUY or SELL order and update portfolio state."""

        side = signal.upper()
        if side == "SHORT":
            side = "SELL"
        now = datetime.now(timezone.utc)

        if qty <= 0:
            return self._build_trade(
                ticker=ticker,
                side="BUY" if side == "BUY" else "SELL",
                qty=0,
                price=price,
                status="REJECTED",
                signal=signal,
                reason="Quantity must be positive.",
                realized_pnl=0.0,
                timestamp=now,
            )

        with self.lock:
            if side == "BUY":
                return self._buy(
                    ticker=ticker,
                    price=price,
                    qty=qty,
                    signal=signal,
                    now=now,
                    stop_loss=stop_loss,
                    target_price=target_price,
                )
            if side == "SELL":
                return self._sell(
                    ticker=ticker,
                    price=price,
                    qty=qty,
                    signal=signal,
                    now=now,
                    stop_loss=stop_loss,
                    target_price=target_price,
                )
            return self._build_trade(
                ticker=ticker,
                side="BUY",
                qty=0,
                price=price,
                status="REJECTED",
                signal=signal,
                reason=f"Unsupported signal '{signal}'.",
                realized_pnl=0.0,
                timestamp=now,
            )

    def calculate_pnl(self, current_prices: dict[str, float]) -> PnLResponseModel:
        """Calculate current and historical PnL using the latest market prices."""

        snapshot = self.record_snapshot(current_prices)
        return PnLResponseModel(current=snapshot, history=self.state.get_history())

    def record_snapshot(self, current_prices: dict[str, float]) -> PnLSnapshotModel:
        """Persist a mark-to-market snapshot for intraday charting."""

        portfolio = self.get_portfolio(current_prices)
        snapshot = PnLSnapshotModel(
            timestamp=datetime.now(timezone.utc),
            total_value=portfolio.total_value,
            cash=portfolio.cash,
            market_value=portfolio.market_value,
            realized_pnl=portfolio.realized_pnl,
            unrealized_pnl=portfolio.unrealized_pnl,
        )
        # Keep a truly fresh account clean until there is actual trading activity.
        if not self.positions and not self.state.get_trades():
            return snapshot
        self.state.add_snapshot(snapshot)
        if self.persistence:
            self.persistence.save_snapshot(self.active_market, snapshot)
        return snapshot

    def get_portfolio(self, current_prices: dict[str, float] | None = None) -> PortfolioModel:
        """Return current portfolio state enriched with market values."""

        current_prices = current_prices or {}

        with self.lock:
            latest_actions: dict[str, str] = {}
            realized_pnl = 0.0
            for trade in self.state.get_trades():
                if trade.status == "FILLED":
                    latest_actions[trade.ticker] = trade.side
                    if trade.timestamp >= self.session_started_at:
                        realized_pnl += trade.realized_pnl

            positions: list[PositionModel] = []
            invested_value = 0.0
            market_value = 0.0
            unrealized_pnl = 0.0

            for ticker, position in self.positions.items():
                market_price = float(current_prices.get(ticker, position.avg_price))
                position_cost = position.avg_price * position.qty
                if position.side == "LONG":
                    position_market_value = market_price * position.qty
                    position_unrealized = (market_price - position.avg_price) * position.qty
                else:
                    position_market_value = -market_price * position.qty
                    position_unrealized = (position.avg_price - market_price) * position.qty

                invested_value += position_cost
                market_value += position_market_value
                unrealized_pnl += position_unrealized

                positions.append(
                    PositionModel(
                        ticker=ticker,
                        qty=position.qty,
                        avg_price=position.avg_price,
                        side=position.side,
                        last_action=latest_actions.get(ticker, "BUY"),
                        market_price=market_price,
                        market_value=position_market_value,
                        unrealized_pnl=position_unrealized,
                        realized_pnl=position.realized_pnl,
                        last_updated=position.last_updated,
                    )
                )

            total_value = self.cash + market_value
            portfolio = PortfolioModel(
                initial_capital=self.initial_capital,
                cash=self.cash,
                invested_value=invested_value,
                market_value=market_value,
                total_value=total_value,
                realized_pnl=realized_pnl,
                unrealized_pnl=unrealized_pnl,
                positions=sorted(positions, key=lambda item: item.ticker),
                trade_count=len(self.state.get_trades()),
                updated_at=self.updated_at,
            )
            return portfolio

    def restore_state(
        self,
        *,
        market: str,
        initial_capital: float,
        cash: float,
        updated_at: datetime,
        session_started_at: datetime,
        last_settlement_date: date | None,
        positions: list[PositionModel],
    ) -> None:
        """Restore engine state from persistent storage."""

        with self.lock:
            self.active_market = market
            self.initial_capital = float(initial_capital)
            self.cash = cash
            self.updated_at = updated_at
            self.session_started_at = session_started_at
            self.last_settlement_date = last_settlement_date
            self.positions = {
                position.ticker: Position(
                    ticker=position.ticker,
                    qty=position.qty,
                    avg_price=position.avg_price,
                    side=position.side,
                    stop_loss=None,
                    target_price=None,
                    realized_pnl=position.realized_pnl,
                    last_updated=position.last_updated,
                )
                for position in positions
            }

    def settle_market_close(
        self,
        *,
        session_date: date,
        current_prices: dict[str, float],
    ) -> DailyInvestmentRecordModel | None:
        """Roll the closing portfolio value into next session capital once per market day."""

        with self.lock:
            if self.last_settlement_date == session_date:
                return None

            portfolio = self.get_portfolio(current_prices)
            settled_at = datetime.now(timezone.utc)
            ending_capital = portfolio.total_value
            record = DailyInvestmentRecordModel(
                session_date=session_date,
                starting_capital=portfolio.initial_capital,
                closing_cash=portfolio.cash,
                closing_market_value=portfolio.market_value,
                ending_capital=ending_capital,
                realized_pnl=portfolio.realized_pnl,
                unrealized_pnl=portfolio.unrealized_pnl,
                net_pnl=ending_capital - portfolio.initial_capital,
                positions_closed=len(portfolio.positions),
                settled_at=settled_at,
            )

            self.positions = {}
            self.cash = ending_capital
            self.initial_capital = ending_capital
            self.updated_at = settled_at
            self.session_started_at = settled_at
            self.last_settlement_date = session_date

            if self.persistence:
                self.persistence.save_daily_investment(self.active_market, record)
                self.persistence.save_portfolio(
                    self.active_market,
                    self.get_portfolio(),
                    session_started_at=self.session_started_at,
                    last_settlement_date=self.last_settlement_date,
                )

            logger.info(
                "Settled market close for %s with ending capital %.2f",
                session_date.isoformat(),
                ending_capital,
            )
            return record

    def _buy(
        self,
        ticker: str,
        price: float,
        qty: int,
        signal: str,
        now: datetime,
        *,
        stop_loss: float | None = None,
        target_price: float | None = None,
    ) -> TradeModel:
        current = self.positions.get(ticker)

        if current and current.side == "SHORT":
            return self._cover_short(
                ticker=ticker,
                price=price,
                qty=qty,
                signal=signal,
                now=now,
                stop_loss=stop_loss,
                target_price=target_price,
            )

        cost = price * qty
        if cost > self.cash:
            return self._build_trade(
                ticker=ticker,
                side="BUY",
                qty=qty,
                price=price,
                status="REJECTED",
                signal=signal,
                reason="Insufficient cash for order.",
                realized_pnl=0.0,
                timestamp=now,
            )

        if current:
            total_qty = current.qty + qty
            current.avg_price = ((current.avg_price * current.qty) + cost) / total_qty
            current.qty = total_qty
            current.stop_loss = stop_loss if stop_loss is not None else current.stop_loss
            current.target_price = target_price if target_price is not None else current.target_price
            current.last_updated = now
        else:
            self.positions[ticker] = Position(
                ticker=ticker,
                qty=qty,
                avg_price=price,
                side="LONG",
                last_updated=now,
                stop_loss=stop_loss,
                target_price=target_price,
            )

        self.cash -= cost
        self.updated_at = now
        logger.info("Filled BUY %s x%s @ %.2f", ticker, qty, price)
        return self._build_trade(
            ticker=ticker,
            side="BUY",
            qty=qty,
            price=price,
            status="FILLED",
            signal=signal,
            reason="Order executed.",
            realized_pnl=0.0,
            timestamp=now,
        )

    def _sell(
        self,
        ticker: str,
        price: float,
        qty: int,
        signal: str,
        now: datetime,
        *,
        stop_loss: float | None = None,
        target_price: float | None = None,
    ) -> TradeModel:
        current = self.positions.get(ticker)
        if current and current.side == "SHORT":
            proceeds = price * qty
            total_qty = current.qty + qty
            current.avg_price = ((current.avg_price * current.qty) + proceeds) / total_qty
            current.qty = total_qty
            current.stop_loss = stop_loss if stop_loss is not None else current.stop_loss
            current.target_price = target_price if target_price is not None else current.target_price
            current.last_updated = now
            self.cash += proceeds
            self.updated_at = now
            logger.info("Filled SELL(short add) %s x%s @ %.2f", ticker, qty, price)
            return self._build_trade(
                ticker=ticker,
                side="SELL",
                qty=qty,
                price=price,
                status="FILLED",
                signal=signal,
                reason="Short position increased.",
                realized_pnl=0.0,
                timestamp=now,
            )

        if not current:
            self.positions[ticker] = Position(
                ticker=ticker,
                qty=qty,
                avg_price=price,
                side="SHORT",
                last_updated=now,
                stop_loss=stop_loss,
                target_price=target_price,
            )
            self.cash += qty * price
            self.updated_at = now
            logger.info("Filled SELL(short open) %s x%s @ %.2f", ticker, qty, price)
            return self._build_trade(
                ticker=ticker,
                side="SELL",
                qty=qty,
                price=price,
                status="FILLED",
                signal=signal,
                reason="Short position opened.",
                realized_pnl=0.0,
                timestamp=now,
            )

        sell_qty = min(qty, current.qty)
        realized_pnl = (price - current.avg_price) * sell_qty
        current.qty -= sell_qty
        current.realized_pnl += realized_pnl
        current.last_updated = now
        self.cash += qty * price

        if current.qty == 0:
            del self.positions[ticker]
            reverse_qty = qty - sell_qty
            if reverse_qty > 0:
                self.positions[ticker] = Position(
                    ticker=ticker,
                    qty=reverse_qty,
                    avg_price=price,
                    side="SHORT",
                    stop_loss=stop_loss,
                    target_price=target_price,
                    last_updated=now,
                )
        elif qty > sell_qty:
            reverse_qty = qty - sell_qty
            self.positions[ticker] = Position(
                ticker=ticker,
                qty=reverse_qty,
                avg_price=price,
                side="SHORT",
                stop_loss=stop_loss,
                target_price=target_price,
                realized_pnl=current.realized_pnl,
                last_updated=now,
            )

        self.updated_at = now
        logger.info("Filled SELL %s x%s @ %.2f", ticker, sell_qty, price)
        return self._build_trade(
            ticker=ticker,
            side="SELL",
            qty=sell_qty,
            price=price,
            status="FILLED",
            signal=signal,
            reason="Order executed.",
            realized_pnl=realized_pnl,
            timestamp=now,
        )

    def _cover_short(
        self,
        ticker: str,
        price: float,
        qty: int,
        signal: str,
        now: datetime,
        *,
        stop_loss: float | None = None,
        target_price: float | None = None,
    ) -> TradeModel:
        current = self.positions[ticker]
        cover_qty = min(qty, current.qty)
        realized_pnl = (current.avg_price - price) * cover_qty
        current.qty -= cover_qty
        current.realized_pnl += realized_pnl
        current.last_updated = now
        self.cash -= qty * price

        if current.qty == 0:
            del self.positions[ticker]
            reverse_qty = qty - cover_qty
            if reverse_qty > 0:
                self.positions[ticker] = Position(
                    ticker=ticker,
                    qty=reverse_qty,
                    avg_price=price,
                    side="LONG",
                    stop_loss=stop_loss,
                    target_price=target_price,
                    last_updated=now,
                )
        elif qty > cover_qty:
            reverse_qty = qty - cover_qty
            self.positions[ticker] = Position(
                ticker=ticker,
                qty=reverse_qty,
                avg_price=price,
                side="LONG",
                stop_loss=stop_loss,
                target_price=target_price,
                realized_pnl=current.realized_pnl,
                last_updated=now,
            )

        self.updated_at = now
        logger.info("Filled BUY(cover) %s x%s @ %.2f", ticker, cover_qty, price)
        return self._build_trade(
            ticker=ticker,
            side="BUY",
            qty=qty,
            price=price,
            status="FILLED",
            signal=signal,
            reason="Short position covered." if qty <= cover_qty else "Short covered and long opened.",
            realized_pnl=realized_pnl,
            timestamp=now,
        )

    def _build_trade(
        self,
        *,
        ticker: str,
        side: str,
        qty: int,
        price: float,
        status: str,
        signal: str,
        reason: str,
        realized_pnl: float,
        timestamp: datetime,
    ) -> TradeModel:
        trade = TradeModel(
            trade_id=uuid4().hex,
            ticker=ticker,
            side=side,
            qty=qty,
            price=price,
            value=qty * price,
            status=status,
            reason=reason,
            signal=signal,
            timestamp=timestamp,
            realized_pnl=realized_pnl,
        )
        self.state.add_trade(trade)
        if self.persistence:
            self.persistence.save_trade(self.active_market, trade)
            self.persistence.save_portfolio(
                self.active_market,
                self.get_portfolio(),
                session_started_at=self.session_started_at,
                last_settlement_date=self.last_settlement_date,
            )
        return trade
