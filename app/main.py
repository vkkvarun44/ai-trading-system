"""FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.dependencies import bootstrap_state, market_profile_manager, persistence, watchlist_manager
from app.services.market_hours import is_regular_market_open
from app.services.trading_cycle import run_trading_cycle, settle_after_market_close
from app.routes.health import router as health_router
from app.routes.market import router as market_router
from app.routes.signal import router as signal_router
from app.routes.trades import router as trades_router
from core.config import settings
from core.logger import get_logger

logger = get_logger(__name__)


async def _auto_execution_loop() -> None:
    """Continuously run the paper-trading cycle on a fixed cadence."""

    while True:
        market_open = is_regular_market_open()
        if not market_open:
            profile = market_profile_manager.get_active_profile()
            logger.info(
                "%s market closed in %s. Auto execution is idle.",
                profile.key,
                profile.timezone,
            )
            try:
                await asyncio.to_thread(settle_after_market_close)
            except Exception as exc:
                logger.exception("Market close settlement failed: %s", exc)
        else:
            try:
                await asyncio.to_thread(run_trading_cycle)
            except Exception as exc:
                logger.exception("Automatic trading cycle failed: %s", exc)
        await asyncio.sleep(settings.auto_execute_interval_seconds)


async def _watchlist_refresh_loop() -> None:
    """Refresh the active market watchlist during market hours on a 15-minute cadence."""

    while True:
        profile = market_profile_manager.get_active_profile()
        try:
            if is_regular_market_open() and watchlist_manager.should_refresh_market_watchlist(
                profile.key,
                profile.timezone,
            ):
                logger.info("Refreshing %s watchlist from the market universe", profile.key)
                result = watchlist_manager.build_and_save_watchlist(profile.key, persistence)
                market_profile_manager.set_watchlist(profile.key, result.tickers)
        except Exception as exc:
            logger.exception("Automatic watchlist refresh failed: %s", exc)
        await asyncio.sleep(min(settings.auto_watchlist_refresh_seconds, 60))


@asynccontextmanager
async def lifespan(_: FastAPI):
    task: asyncio.Task | None = None
    watchlist_task: asyncio.Task | None = None
    bootstrap_state()
    watchlist_task = asyncio.create_task(_watchlist_refresh_loop())
    if settings.auto_execute_enabled:
        logger.info(
            "Auto execution enabled with %s second interval",
            settings.auto_execute_interval_seconds,
        )
        if settings.auto_execute_only_when_market_open:
            profile = market_profile_manager.get_active_profile()
            logger.info(
                "Auto execution restricted to %s market hours: %s to %s (%s)",
                profile.key,
                profile.open_time.isoformat(timespec="minutes"),
                profile.close_time.isoformat(timespec="minutes"),
                profile.timezone,
            )
        task = asyncio.create_task(_auto_execution_loop())
    else:
        logger.info("Auto execution disabled")

    try:
        yield
    finally:
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.info("Auto execution loop stopped")
        if watchlist_task:
            watchlist_task.cancel()
            try:
                await watchlist_task
            except asyncio.CancelledError:
                logger.info("Watchlist refresh loop stopped")
        persistence.shutdown()


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(market_router)
app.include_router(signal_router)
app.include_router(trades_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "AI Trading Paper Engine is running."}
