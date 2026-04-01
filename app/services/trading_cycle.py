"""Shared trading-cycle orchestration for automatic execution."""

from __future__ import annotations

from app.dependencies import paper_engine, signal_executor
from app.routes.signal import refresh_signals
from core.logger import get_logger
from db.models import PortfolioModel, TradeModel
from market.yahoo_scanner import get_latest_prices

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

    synced_signals = [
        signal.model_copy(update={"price": prices.get(signal.ticker, signal.price)})
        for signal in signals
    ]

    signal_orders = signal_executor.execute_signals(synced_signals, force=force)
    risk_exits = signal_executor.generate_exit_signals(prices)
    risk_orders = signal_executor.execute_signals(risk_exits, force=True)
    portfolio = paper_engine.get_portfolio(prices)
    orders = [*signal_orders, *risk_orders]
    logger.info("Trading cycle completed with %s orders", len(orders))
    return orders, portfolio
