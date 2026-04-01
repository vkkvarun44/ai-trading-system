"""Signal routes."""

from fastapi import APIRouter

from app.dependencies import state
from app.services.market_hours import is_regular_market_open
from core.config import settings
from db.models import SignalModel
from market.yahoo_scanner import compute_top_movers
from signals.signal_engine import generate_signals

router = APIRouter(tags=["signals"])


def refresh_signals() -> list[SignalModel]:
    if not is_regular_market_open():
        state.update_signals([])
        return []

    movers = compute_top_movers(settings.watchlist, limit=settings.signal_top_movers_limit)
    signal_universe = [*movers["gainers"], *movers["losers"]]
    signals = generate_signals(signal_universe)
    state.update_signals(signals)
    return signals


@router.get("/signals", response_model=list[SignalModel])
def get_signals() -> list[SignalModel]:
    if not is_regular_market_open():
        state.update_signals([])
        return []

    cached = state.get_signals()
    if cached:
        return cached
    return refresh_signals()
