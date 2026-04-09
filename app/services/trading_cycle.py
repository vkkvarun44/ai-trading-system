"""Shared trading-cycle orchestration for automatic execution."""

from __future__ import annotations

from app.services.market_hours import get_latest_completed_session_date, should_exit_before_market_close
from app.dependencies import paper_engine, signal_executor
from app.routes.signal import refresh_signals
from core.logger import get_logger
from db.models import PortfolioModel, TradeModel
from markets.yahoo_scanner import get_latest_prices

logger = get_logger(__name__)


def run_trading_cycle(
    *,
    tickers: list[str] | None = None,
    force: bool = False,
) -> tuple[list[TradeModel], PortfolioModel]:
    """Run one end-to-end trading cycle."""

    signals = refresh_signals()
    if tickers:
        selected = set(tickers)
        signals = [signal for signal in signals if signal.ticker in selected]

    universe = {signal.ticker for signal in signals}
    universe.update(position.ticker for position in paper_engine.get_portfolio().positions)
    prices = get_latest_prices(sorted(universe))

    if should_exit_before_market_close():
        eod_orders = signal_executor.close_positions_for_end_of_day(prices)
        paper_engine.record_snapshot(prices)
        portfolio = paper_engine.get_portfolio(prices)
        logger.info("Trading cycle flattened %s positions for end-of-day exit", len(eod_orders))
        return eod_orders, portfolio

    synced_signals = [
        signal.model_copy(update={"price": prices.get(signal.ticker, signal.price)})
        for signal in signals
    ]

    risk_exits = signal_executor.generate_exit_signals(prices)
    risk_orders = signal_executor.execute_signals(risk_exits, force=True)
    signal_orders = signal_executor.execute_signals(synced_signals, force=force)
    paper_engine.record_snapshot(prices)
    portfolio = paper_engine.get_portfolio(prices)
    orders = [*signal_orders, *risk_orders]
    logger.info("Trading cycle completed with %s orders", len(orders))
    return orders, portfolio


def settle_after_market_close() -> None:
    """Finalize the previous session and reset capital for the next trading day."""

    tickers = [position.ticker for position in paper_engine.get_portfolio().positions]
    prices = get_latest_prices(tickers)
    record = paper_engine.settle_market_close(
        session_date=get_latest_completed_session_date(),
        current_prices=prices,
    )
    if record is None:
        logger.debug("Market close settlement already processed for the latest session")
