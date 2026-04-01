"""Application service container."""

from __future__ import annotations

from core.config import settings
from db.persistence import PersistenceManager
from execution.paper_trader import PaperTradingEngine
from execution.signal_executor import SignalExecutor
from state.store import TradingState

state = TradingState()
persistence = PersistenceManager()
paper_engine = PaperTradingEngine(
    initial_capital=settings.initial_capital,
    state=state,
    persistence=persistence,
)
signal_executor = SignalExecutor(engine=paper_engine, state=state, settings=settings)


def bootstrap_state() -> None:
    """Load persisted portfolio and trade data into memory."""

    persistence.initialize()
    cash, updated_at, positions, trades, pnl_history = persistence.load_state()
    paper_engine.restore_state(cash=cash, updated_at=updated_at, positions=positions)
    state.load_trades(trades)
    state.load_history(pnl_history)
