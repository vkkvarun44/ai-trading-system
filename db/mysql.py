"""MySQL persistence for trades, positions, and portfolio snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from peewee import (
    AutoField,
    CharField,
    DateTimeField,
    DecimalField,
    IntegerField,
    Model,
    MySQLDatabase,
    TextField,
)

from core.config import settings
from core.logger import get_logger
from db.models import PnLSnapshotModel, PortfolioModel, PositionModel, TradeModel

logger = get_logger(__name__)

database = MySQLDatabase(
    settings.mysql_database,
    host=settings.mysql_host,
    port=settings.mysql_port,
    user=settings.mysql_user,
    password=settings.mysql_password,
)


class BaseModel(Model):
    class Meta:
        database = database


class TradeRecord(BaseModel):
    trade_id = CharField(primary_key=True, max_length=64)
    ticker = CharField(max_length=32, index=True)
    side = CharField(max_length=8)
    qty = IntegerField()
    price = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    value = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    status = CharField(max_length=16)
    reason = TextField()
    signal = CharField(max_length=32)
    timestamp = DateTimeField(index=True)
    realized_pnl = DecimalField(max_digits=18, decimal_places=6, auto_round=True, default=0)

    class Meta:
        table_name = "trades"


class PositionRecord(BaseModel):
    ticker = CharField(primary_key=True, max_length=32)
    qty = IntegerField()
    avg_price = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    side = CharField(max_length=8, default="LONG")
    realized_pnl = DecimalField(max_digits=18, decimal_places=6, auto_round=True, default=0)
    last_updated = DateTimeField()

    class Meta:
        table_name = "positions"


class PortfolioRecord(BaseModel):
    id = IntegerField(primary_key=True)
    initial_capital = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    cash = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    updated_at = DateTimeField()

    class Meta:
        table_name = "portfolio"


class PnLSnapshotRecord(BaseModel):
    id = AutoField()
    timestamp = DateTimeField(index=True)
    total_value = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    cash = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    market_value = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    realized_pnl = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    unrealized_pnl = DecimalField(max_digits=18, decimal_places=6, auto_round=True)

    class Meta:
        table_name = "pnl_snapshots"


TABLES = [TradeRecord, PositionRecord, PortfolioRecord, PnLSnapshotRecord]


def connect() -> None:
    """Open a DB connection and ensure tables exist."""

    if database.is_closed():
        database.connect(reuse_if_open=True)
    database.create_tables(TABLES, safe=True)
    _ensure_schema()
    logger.info("Connected to MySQL database '%s'", settings.mysql_database)


def close() -> None:
    """Close the DB connection if open."""

    if not database.is_closed():
        database.close()


def save_trade(trade: TradeModel) -> None:
    TradeRecord.insert(
        trade_id=trade.trade_id,
        ticker=trade.ticker,
        side=trade.side,
        qty=trade.qty,
        price=trade.price,
        value=trade.value,
        status=trade.status,
        reason=trade.reason,
        signal=trade.signal,
        timestamp=trade.timestamp,
        realized_pnl=trade.realized_pnl,
    ).on_conflict_replace().execute()


def save_portfolio_state(portfolio: PortfolioModel) -> None:
    PortfolioRecord.insert(
        id=1,
        initial_capital=portfolio.initial_capital,
        cash=portfolio.cash,
        updated_at=portfolio.updated_at,
    ).on_conflict_replace().execute()

    existing = {position.ticker for position in PositionRecord.select(PositionRecord.ticker)}
    incoming = {position.ticker for position in portfolio.positions}

    stale = existing - incoming
    if stale:
        PositionRecord.delete().where(PositionRecord.ticker.in_(stale)).execute()

    for position in portfolio.positions:
        PositionRecord.insert(
            ticker=position.ticker,
            qty=position.qty,
            avg_price=position.avg_price,
            side=position.side,
            realized_pnl=position.realized_pnl,
            last_updated=position.last_updated,
        ).on_conflict_replace().execute()


def save_pnl_snapshot(snapshot: PnLSnapshotModel) -> None:
    PnLSnapshotRecord.insert(
        timestamp=snapshot.timestamp,
        total_value=snapshot.total_value,
        cash=snapshot.cash,
        market_value=snapshot.market_value,
        realized_pnl=snapshot.realized_pnl,
        unrealized_pnl=snapshot.unrealized_pnl,
    ).execute()

    query = (
        PnLSnapshotRecord.select(PnLSnapshotRecord.id)
        .order_by(PnLSnapshotRecord.timestamp.desc())
        .offset(settings.pnl_history_limit)
    )
    stale_ids = [record.id for record in query]
    if stale_ids:
        PnLSnapshotRecord.delete().where(PnLSnapshotRecord.id.in_(stale_ids)).execute()


def load_trades() -> list[TradeModel]:
    rows = TradeRecord.select().order_by(TradeRecord.timestamp)
    return [
        TradeModel(
            trade_id=row.trade_id,
            ticker=row.ticker,
            side=row.side,
            qty=row.qty,
            price=_to_float(row.price),
            value=_to_float(row.value),
            status=row.status,
            reason=row.reason,
            signal=row.signal,
            timestamp=_to_utc(row.timestamp),
            realized_pnl=_to_float(row.realized_pnl),
        )
        for row in rows
    ]


def load_positions() -> list[PositionModel]:
    rows = PositionRecord.select().order_by(PositionRecord.ticker)
    return [
        PositionModel(
            ticker=row.ticker,
            qty=row.qty,
            avg_price=_to_float(row.avg_price),
            side=row.side,
            realized_pnl=_to_float(row.realized_pnl),
            last_updated=_to_utc(row.last_updated),
        )
        for row in rows
    ]


def load_portfolio_cash(initial_capital: float) -> tuple[float, datetime]:
    record = PortfolioRecord.get_or_none(PortfolioRecord.id == 1)
    if not record:
        now = datetime.now(timezone.utc)
        return initial_capital, now
    return _to_float(record.cash), _to_utc(record.updated_at)


def load_pnl_history() -> list[PnLSnapshotModel]:
    rows = PnLSnapshotRecord.select().order_by(PnLSnapshotRecord.timestamp)
    return [
        PnLSnapshotModel(
            timestamp=_to_utc(row.timestamp),
            total_value=_to_float(row.total_value),
            cash=_to_float(row.cash),
            market_value=_to_float(row.market_value),
            realized_pnl=_to_float(row.realized_pnl),
            unrealized_pnl=_to_float(row.unrealized_pnl),
        )
        for row in rows
    ]


def _to_float(value: Decimal | float | int) -> float:
    return float(value)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _ensure_schema() -> None:
    """Repair important schema details for already-created tables."""

    database.execute_sql(
        """
        ALTER TABLE pnl_snapshots
        MODIFY COLUMN id INT NOT NULL AUTO_INCREMENT
        """
    )
    try:
        database.execute_sql(
            """
            ALTER TABLE positions
            ADD COLUMN side VARCHAR(8) NOT NULL DEFAULT 'LONG'
            """
        )
    except Exception:
        pass
