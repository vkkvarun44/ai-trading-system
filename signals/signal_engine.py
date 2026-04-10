"""Signal generation pipeline."""

from __future__ import annotations

from db.models import MarketMover, SignalModel
from signals.filter_pipeline import filter_stocks


def generate_signals(stocks: list[MarketMover], model=None) -> list[SignalModel]:
    """Generate strategy signals for the supplied market movers."""

    accepted, _rejected = filter_stocks(stocks, model=model)
    return accepted
