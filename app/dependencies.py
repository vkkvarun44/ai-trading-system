"""Application service container."""

from __future__ import annotations

from app.services.market_profile import MarketProfileManager
from app.services.watchlist_manager import WatchlistManager
from core.config import settings
from db.persistence import PersistenceManager
from execution.paper_trader import PaperTradingEngine
from execution.signal_executor import SignalExecutor
from state.store import TradingState

state = TradingState()
persistence = PersistenceManager()
market_profile_manager = MarketProfileManager()
watchlist_manager = WatchlistManager()
paper_engine = PaperTradingEngine(
    initial_capital=settings.initial_capital,
    state=state,
    persistence=persistence,
)
signal_executor = SignalExecutor(engine=paper_engine, state=state, settings=settings)


def bootstrap_state() -> None:
    """Load persisted portfolio and trade data into memory."""

    persistence.initialize()
    watchlist_manager.initialize(persistence)
    for market in ("US", "INDIA"):
        market_profile_manager.set_watchlist(market, watchlist_manager.get_watchlist(market))
    load_market_state(market_profile_manager.get_active_profile().key)


def load_market_state(market: str) -> None:
    """Load one market ledger into the in-memory engine and state."""

    (
        initial_capital,
        cash,
        updated_at,
        session_started_at,
        last_settlement_date,
        positions,
        trades,
        pnl_history,
    ) = persistence.load_state(market)
    paper_engine.restore_state(
        market=market,
        initial_capital=initial_capital,
        cash=cash,
        updated_at=updated_at,
        session_started_at=session_started_at,
        last_settlement_date=last_settlement_date,
        positions=positions,
    )
    state.reset_for_market(trades=trades, history=pnl_history)


def switch_active_market(market: str) -> None:
    """Switch the runtime market profile and load its independent ledger."""

    market_profile_manager.set_active_market(market)
    load_market_state(market_profile_manager.get_active_profile().key)
