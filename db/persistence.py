"""Persistence adapter for loading and saving trading state."""

from __future__ import annotations

from datetime import datetime, timezone

from core.config import settings
from core.logger import get_logger
from db.models import PnLSnapshotModel, PortfolioModel, PositionModel, TradeModel

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

    def load_state(self) -> tuple[float, datetime, list[PositionModel], list[TradeModel], list[PnLSnapshotModel]]:
        if not self.enabled:
            return (
                settings.initial_capital,
                datetime.now(timezone.utc),
                [],
                [],
                [],
            )
        cash, updated_at = mysql_store.load_portfolio_cash(settings.initial_capital)
        return (
            cash,
            updated_at,
            mysql_store.load_positions(),
            mysql_store.load_trades(),
            mysql_store.load_pnl_history(),
        )

    def save_trade(self, trade: TradeModel) -> None:
        if self.enabled:
            mysql_store.save_trade(trade)

    def save_portfolio(self, portfolio: PortfolioModel) -> None:
        if self.enabled:
            mysql_store.save_portfolio_state(portfolio)

    def save_snapshot(self, snapshot: PnLSnapshotModel) -> None:
        if self.enabled:
            mysql_store.save_pnl_snapshot(snapshot)
