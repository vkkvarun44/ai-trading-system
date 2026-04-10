"""Signal routes."""

from fastapi import APIRouter

from app.dependencies import market_profile_manager, state, watchlist_manager
from app.services.market_hours import is_regular_market_open
from core.config import settings
from db.models import SignalModel
from markets.yahoo_scanner import rank_stocks
from signals.signal_engine import generate_signals

router = APIRouter(tags=["signals"])


def refresh_signals() -> list[SignalModel]:
    if not is_regular_market_open():
        state.update_signals([])
        return []

    ranked_candidates = rank_stocks(
        watchlist_manager.get_watchlist(market_profile_manager.get_active_profile().key),
        top_n=3,
        min_price=settings.auto_watchlist_min_price,
        min_avg_volume=settings.auto_watchlist_min_avg_volume,
    )
    signal_universe = [
        candidate
        for candidate in ranked_candidates
        if candidate.rejection_reason is None
    ]
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
