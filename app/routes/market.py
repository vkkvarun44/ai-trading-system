"""Market routes."""

from fastapi import APIRouter, HTTPException

from app.dependencies import market_profile_manager, persistence, switch_active_market, watchlist_manager
from app.services.market_hours import get_market_status, is_regular_market_open
from core.config import settings
from db.models import (
    AutoWatchlistRequestModel,
    AutoWatchlistResponseModel,
    MarketSelectionRequestModel,
    MarketStatusModel,
    WatchlistPreparationResultModel,
    WatchlistPrepareRequestModel,
    WatchlistResponseModel,
    WatchlistUpdateRequestModel,
)
from markets.yahoo_scanner import compute_top_movers, reset_market_data_cache

router = APIRouter(tags=["market"])


@router.get("/top-movers")
def top_movers() -> dict[str, list[dict]]:
    if not is_regular_market_open():
        return {"gainers": [], "losers": []}

    movers = compute_top_movers(
        watchlist_manager.get_watchlist(market_profile_manager.get_active_profile().key),
        limit=None,
    )
    return {
        "gainers": [item.model_dump() for item in movers["gainers"]],
        "losers": [item.model_dump() for item in movers["losers"]],
    }


@router.get("/market-status", response_model=MarketStatusModel)
def market_status() -> MarketStatusModel:
    return MarketStatusModel(**get_market_status())


@router.put("/market-status", response_model=MarketStatusModel)
def update_market_status(payload: MarketSelectionRequestModel) -> MarketStatusModel:
    try:
        switch_active_market(payload.market)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    reset_market_data_cache()
    return MarketStatusModel(**get_market_status())


@router.get("/watchlist", response_model=WatchlistResponseModel)
def get_watchlist(market: str | None = None) -> WatchlistResponseModel:
    market_key = (market or market_profile_manager.get_active_profile().key).upper()
    tickers = watchlist_manager.get_watchlist(market_key)
    return WatchlistResponseModel(
        market=market_key,
        tickers=tickers,
        count=len(tickers),
        last_refreshed_at=watchlist_manager.get_last_refreshed_at(market_key),
        refresh_interval_seconds=settings.auto_watchlist_refresh_seconds,
    )


@router.post("/watchlist/prepare", response_model=WatchlistPreparationResultModel)
def prepare_watchlist(payload: WatchlistPrepareRequestModel) -> WatchlistPreparationResultModel:
    prepared, invalid = watchlist_manager.prepare_watchlist(payload.market, payload.tickers)
    return WatchlistPreparationResultModel(
        market=payload.market,
        input_count=len(payload.tickers),
        prepared_count=len(prepared),
        tickers=prepared,
        invalid_tickers=invalid,
    )


@router.put("/watchlist", response_model=WatchlistPreparationResultModel)
def update_watchlist(payload: WatchlistUpdateRequestModel) -> WatchlistPreparationResultModel:
    prepared, invalid = watchlist_manager.save_prepared_watchlist(
        payload.market,
        payload.tickers,
        persistence,
    )
    market_profile_manager.set_watchlist(payload.market, prepared)
    if market_profile_manager.get_active_profile().key == payload.market:
        reset_market_data_cache()
    return WatchlistPreparationResultModel(
        market=payload.market,
        input_count=len(payload.tickers),
        prepared_count=len(prepared),
        tickers=prepared,
        invalid_tickers=invalid,
    )


@router.post("/watchlist/auto-build", response_model=AutoWatchlistResponseModel)
def auto_build_watchlist(payload: AutoWatchlistRequestModel) -> AutoWatchlistResponseModel:
    return watchlist_manager.build_watchlist(payload.market, target_size=payload.target_size)


@router.put("/watchlist/auto-build", response_model=AutoWatchlistResponseModel)
def save_auto_built_watchlist(payload: AutoWatchlistRequestModel) -> AutoWatchlistResponseModel:
    result = watchlist_manager.build_and_save_watchlist(
        payload.market,
        persistence,
        target_size=payload.target_size,
    )
    market_profile_manager.set_watchlist(payload.market, result.tickers)
    if market_profile_manager.get_active_profile().key == payload.market:
        reset_market_data_cache()
    return result
