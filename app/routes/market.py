"""Market routes."""

from fastapi import APIRouter

from app.services.market_hours import get_market_status, is_regular_market_open
from core.config import settings
from market.yahoo_scanner import compute_top_movers

router = APIRouter(tags=["market"])


@router.get("/top-movers")
def top_movers() -> dict[str, list[dict]]:
    if not is_regular_market_open():
        return {"gainers": [], "losers": []}

    movers = compute_top_movers(settings.watchlist, limit=None)
    return {
        "gainers": [item.model_dump() for item in movers["gainers"]],
        "losers": [item.model_dump() for item in movers["losers"]],
    }


@router.get("/market-status")
def market_status() -> dict[str, str | bool]:
    return get_market_status()
