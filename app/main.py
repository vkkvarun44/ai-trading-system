"""FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.dependencies import bootstrap_state, persistence
from app.services.market_hours import is_regular_market_open
from app.services.trading_cycle import run_trading_cycle
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
        if settings.auto_execute_only_when_market_open and not is_regular_market_open():
            logger.info("Market closed in %s. Auto execution is idle.", settings.market_timezone)
        else:
            try:
                await asyncio.to_thread(run_trading_cycle)
            except Exception as exc:
                logger.exception("Automatic trading cycle failed: %s", exc)
        await asyncio.sleep(settings.auto_execute_interval_seconds)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task: asyncio.Task | None = None
    bootstrap_state()
    if settings.auto_execute_enabled:
        logger.info(
            "Auto execution enabled with %s second interval",
            settings.auto_execute_interval_seconds,
        )
        if settings.auto_execute_only_when_market_open:
            logger.info(
                "Auto execution restricted to regular market hours: %s to %s (%s)",
                settings.market_open_time.isoformat(timespec="minutes"),
                settings.market_close_time.isoformat(timespec="minutes"),
                settings.market_timezone,
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
