"""Persistence adapter for loading and saving trading state."""

from __future__ import annotations

from datetime import date, datetime, timezone

from core.config import settings
from core.logger import get_logger
from db.models import (
    DailyInvestmentRecordModel,
    PnLSnapshotModel,
    PortfolioModel,
    PositionModel,
    TradeModel,
)

logger = get_logger(__name__)

try:
    import pymysql  # type: ignore
except ImportError:  # pragma: no cover
    pymysql = None

mysql_store = None
if pymysql is not None:
    pymysql.install_as_MySQLdb()
    from db import mysql as mysql_store  # noqa: E402


class PersistenceManager:
    """Thin wrapper around MySQL persistence with graceful fallback."""

    def __init__(self) -> None:
        self.enabled = settings.persistence_enabled and mysql_store is not None

    def initialize(self) -> None:
        if not settings.persistence_enabled:
            logger.info("Persistence disabled; using in-memory state only")
            return
        if mysql_store is None:
            logger.warning(
                "Persistence requested but PyMySQL is not installed. "
                "Run `pip install PyMySQL` to enable MySQL storage."
            )
            return
        mysql_store.connect()

    def shutdown(self) -> None:
        if self.enabled:
            mysql_store.close()

    def load_state(
        self,
        market: str,
    ) -> tuple[
        float,
        float,
        datetime,
        datetime,
        date | None,
        list[PositionModel],
        list[TradeModel],
        list[PnLSnapshotModel],
    ]:
        if not self.enabled:
            now = datetime.now(timezone.utc)
            return (
                settings.initial_capital,
                settings.initial_capital,
                now,
                now,
                None,
                [],
                [],
                [],
            )
        initial_capital, cash, updated_at, session_started_at, last_settlement_date = (
            mysql_store.load_portfolio_state(market, settings.initial_capital)
        )
        return (
            initial_capital,
            cash,
            updated_at,
            session_started_at,
            last_settlement_date,
            mysql_store.load_positions(market),
            mysql_store.load_trades(market),
            mysql_store.load_pnl_history(market),
        )

    def save_trade(self, market: str, trade: TradeModel) -> None:
        if self.enabled:
            mysql_store.save_trade(market, trade)

    def save_portfolio(
        self,
        market: str,
        portfolio: PortfolioModel,
        *,
        session_started_at: datetime,
        last_settlement_date: date | None,
    ) -> None:
        if self.enabled:
            mysql_store.save_portfolio_state(
                market,
                portfolio,
                session_started_at=session_started_at,
                last_settlement_date=last_settlement_date,
            )

    def save_snapshot(self, market: str, snapshot: PnLSnapshotModel) -> None:
        if self.enabled:
            mysql_store.save_pnl_snapshot(market, snapshot)

    def save_daily_investment(self, market: str, record: DailyInvestmentRecordModel) -> None:
        if self.enabled:
            mysql_store.save_daily_investment(market, record)

    def load_watchlist(self, market: str) -> list[str]:
        if not self.enabled:
            return []
        return mysql_store.load_watchlist(market)

    def load_watchlist_refreshed_at(self, market: str) -> datetime | None:
        if not self.enabled:
            return None
        return mysql_store.load_watchlist_refreshed_at(market)

    def save_watchlist(self, market: str, tickers: list[str]) -> None:
        if self.enabled:
            mysql_store.save_watchlist(market, tickers)

    def reset_market_state(self, market: str, *, clear_watchlist: bool = False) -> None:
        if self.enabled:
            mysql_store.reset_market_state(market, clear_watchlist=clear_watchlist)
