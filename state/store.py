"""In-memory state storage for paper trading."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock

from db.models import PnLSnapshotModel, SignalModel, TradeModel


@dataclass
class TradingState:
    """Thread-safe in-memory storage for signals, trades, and cooldowns."""

    latest_signals: list[SignalModel] = field(default_factory=list)
    trades: list[TradeModel] = field(default_factory=list)
    pnl_history: list[PnLSnapshotModel] = field(default_factory=list)
    cooldowns: dict[str, datetime] = field(default_factory=dict)
    lock: RLock = field(default_factory=RLock)

    def update_signals(self, signals: list[SignalModel]) -> None:
        with self.lock:
            self.latest_signals = signals

    def get_signals(self) -> list[SignalModel]:
        with self.lock:
            return list(self.latest_signals)

    def add_trade(self, trade: TradeModel) -> None:
        with self.lock:
            self.trades.append(trade)

    def get_trades(self) -> list[TradeModel]:
        with self.lock:
            return list(self.trades)

    def load_trades(self, trades: list[TradeModel]) -> None:
        with self.lock:
            self.trades = list(trades)

    def set_cooldown(self, ticker: str, timestamp: datetime) -> None:
        with self.lock:
            self.cooldowns[ticker] = timestamp

    def get_cooldown(self, ticker: str) -> datetime | None:
        with self.lock:
            return self.cooldowns.get(ticker)

    def add_snapshot(self, snapshot: PnLSnapshotModel, max_items: int = 500) -> None:
        with self.lock:
            self.pnl_history.append(snapshot)
            if len(self.pnl_history) > max_items:
                self.pnl_history = self.pnl_history[-max_items:]

    def get_history(self) -> list[PnLSnapshotModel]:
        with self.lock:
            return list(self.pnl_history)

    def load_history(self, history: list[PnLSnapshotModel]) -> None:
        with self.lock:
            self.pnl_history = list(history)
