"""MySQL persistence for trades, positions, and portfolio snapshots."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from peewee import (
    AutoField,
    CharField,
    DateField,
    DateTimeField,
    DecimalField,
    IntegerField,
    Model,
    MySQLDatabase,
    TextField,
)

from core.config import settings
from core.logger import get_logger
from db.models import DailyInvestmentRecordModel, PnLSnapshotModel, PortfolioModel, PositionModel, TradeModel

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
    market = CharField(max_length=16, index=True, default="US")
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
    market = CharField(max_length=16, index=True, default="US")
    qty = IntegerField()
    avg_price = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    side = CharField(max_length=8, default="LONG")
    realized_pnl = DecimalField(max_digits=18, decimal_places=6, auto_round=True, default=0)
    last_updated = DateTimeField()

    class Meta:
        table_name = "positions"


class PortfolioRecord(BaseModel):
    id = IntegerField(primary_key=True)
    market = CharField(max_length=16, index=True, default="US")
    initial_capital = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    cash = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    updated_at = DateTimeField()
    session_started_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    last_settlement_date = DateField(null=True)

    class Meta:
        table_name = "portfolio"


class PnLSnapshotRecord(BaseModel):
    id = AutoField()
    market = CharField(max_length=16, index=True, default="US")
    timestamp = DateTimeField(index=True)
    total_value = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    cash = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    market_value = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    realized_pnl = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    unrealized_pnl = DecimalField(max_digits=18, decimal_places=6, auto_round=True)

    class Meta:
        table_name = "pnl_snapshots"


class DailyInvestmentRecord(BaseModel):
    id = AutoField()
    market = CharField(max_length=16, index=True, default="US")
    session_date = DateField(index=True)
    starting_capital = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    closing_cash = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    closing_market_value = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    ending_capital = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    realized_pnl = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    unrealized_pnl = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    net_pnl = DecimalField(max_digits=18, decimal_places=6, auto_round=True)
    positions_closed = IntegerField()
    settled_at = DateTimeField(index=True)

    class Meta:
        table_name = "daily_investments"


class WatchlistRecord(BaseModel):
    id = AutoField()
    market = CharField(max_length=16, index=True, default="US")
    ticker = CharField(max_length=32, index=True)
    position = IntegerField(default=0)

    class Meta:
        table_name = "watchlists"


class WatchlistMetaRecord(BaseModel):
    market = CharField(primary_key=True, max_length=16)
    refreshed_at = DateTimeField(null=True)

    class Meta:
        table_name = "watchlist_meta"


TABLES = [
    TradeRecord,
    PositionRecord,
    PortfolioRecord,
    PnLSnapshotRecord,
    DailyInvestmentRecord,
    WatchlistRecord,
    WatchlistMetaRecord,
]


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


def reset_market_state(market: str, *, clear_watchlist: bool = False) -> None:
    """Delete persisted paper-trading state for one market ledger."""

    market_key = market.strip().upper()
    with database.atomic():
        TradeRecord.delete().where(TradeRecord.market == market_key).execute()
        PositionRecord.delete().where(PositionRecord.market == market_key).execute()
        PnLSnapshotRecord.delete().where(PnLSnapshotRecord.market == market_key).execute()
        DailyInvestmentRecord.delete().where(DailyInvestmentRecord.market == market_key).execute()
        PortfolioRecord.delete().where(PortfolioRecord.market == market_key).execute()
        if clear_watchlist:
            WatchlistRecord.delete().where(WatchlistRecord.market == market_key).execute()
            WatchlistMetaRecord.delete().where(WatchlistMetaRecord.market == market_key).execute()


def save_trade(market: str, trade: TradeModel) -> None:
    TradeRecord.insert(
        trade_id=trade.trade_id,
        market=market,
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


def save_portfolio_state(
    market: str,
    portfolio: PortfolioModel,
    *,
    session_started_at: datetime,
    last_settlement_date: date | None,
) -> None:
    PortfolioRecord.insert(
        id=_portfolio_id(market),
        market=market,
        initial_capital=portfolio.initial_capital,
        cash=portfolio.cash,
        updated_at=portfolio.updated_at,
        session_started_at=session_started_at,
        last_settlement_date=last_settlement_date,
    ).on_conflict_replace().execute()

    existing = {
        row.ticker
        for row in PositionRecord.select(PositionRecord.ticker).where(PositionRecord.market == market)
    }
    incoming = {_scoped_ticker(market, position.ticker) for position in portfolio.positions}

    stale = existing - incoming
    if stale:
        PositionRecord.delete().where(
            (PositionRecord.market == market) & (PositionRecord.ticker.in_(stale))
        ).execute()

    for position in portfolio.positions:
        PositionRecord.insert(
            ticker=_scoped_ticker(market, position.ticker),
            market=market,
            qty=position.qty,
            avg_price=position.avg_price,
            side=position.side,
            realized_pnl=position.realized_pnl,
            last_updated=position.last_updated,
        ).on_conflict_replace().execute()


def save_pnl_snapshot(market: str, snapshot: PnLSnapshotModel) -> None:
    PnLSnapshotRecord.insert(
        market=market,
        timestamp=snapshot.timestamp,
        total_value=snapshot.total_value,
        cash=snapshot.cash,
        market_value=snapshot.market_value,
        realized_pnl=snapshot.realized_pnl,
        unrealized_pnl=snapshot.unrealized_pnl,
    ).execute()

    query = (
        PnLSnapshotRecord.select(PnLSnapshotRecord.id)
        .where(PnLSnapshotRecord.market == market)
        .order_by(PnLSnapshotRecord.timestamp.desc())
        .offset(settings.pnl_history_limit)
    )
    stale_ids = [record.id for record in query]
    if stale_ids:
        PnLSnapshotRecord.delete().where(PnLSnapshotRecord.id.in_(stale_ids)).execute()


def save_daily_investment(market: str, record: DailyInvestmentRecordModel) -> None:
    defaults = {
        "starting_capital": record.starting_capital,
        "closing_cash": record.closing_cash,
        "closing_market_value": record.closing_market_value,
        "ending_capital": record.ending_capital,
        "realized_pnl": record.realized_pnl,
        "unrealized_pnl": record.unrealized_pnl,
        "net_pnl": record.net_pnl,
        "positions_closed": record.positions_closed,
        "settled_at": record.settled_at,
    }
    saved, created = DailyInvestmentRecord.get_or_create(
        market=market,
        session_date=record.session_date,
        defaults=defaults,
    )
    if not created:
        (
            DailyInvestmentRecord.update(**defaults)
            .where(
                (DailyInvestmentRecord.market == market)
                & (DailyInvestmentRecord.session_date == record.session_date)
            )
            .execute()
        )


def load_trades(market: str) -> list[TradeModel]:
    rows = TradeRecord.select().where(TradeRecord.market == market).order_by(TradeRecord.timestamp)
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


def load_positions(market: str) -> list[PositionModel]:
    rows = (
        PositionRecord.select()
        .where(PositionRecord.market == market)
        .order_by(PositionRecord.ticker)
    )
    return [
        PositionModel(
            ticker=_unscoped_ticker(market, row.ticker),
            qty=row.qty,
            avg_price=_to_float(row.avg_price),
            side=row.side,
            realized_pnl=_to_float(row.realized_pnl),
            last_updated=_to_utc(row.last_updated),
        )
        for row in rows
    ]


def load_portfolio_state(
    market: str,
    initial_capital: float,
) -> tuple[float, float, datetime, datetime, date | None]:
    record = PortfolioRecord.get_or_none(PortfolioRecord.id == _portfolio_id(market))
    if not record:
        now = datetime.now(timezone.utc)
        return initial_capital, initial_capital, now, now, None
    return (
        _to_float(record.initial_capital),
        _to_float(record.cash),
        _to_utc(record.updated_at),
        _to_utc(record.session_started_at),
        record.last_settlement_date,
    )


def load_pnl_history(market: str) -> list[PnLSnapshotModel]:
    rows = (
        PnLSnapshotRecord.select()
        .where(PnLSnapshotRecord.market == market)
        .order_by(PnLSnapshotRecord.timestamp)
    )
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


def load_watchlist(market: str) -> list[str]:
    rows = (
        WatchlistRecord.select()
        .where(WatchlistRecord.market == market)
        .order_by(WatchlistRecord.position, WatchlistRecord.id)
    )
    return [row.ticker for row in rows]


def save_watchlist(market: str, tickers: list[str]) -> None:
    WatchlistRecord.delete().where(WatchlistRecord.market == market).execute()
    for index, ticker in enumerate(tickers):
        WatchlistRecord.insert(
            market=market,
            ticker=ticker,
            position=index,
        ).execute()
    WatchlistMetaRecord.insert(
        market=market,
        refreshed_at=datetime.now(timezone.utc),
    ).on_conflict_replace().execute()


def load_watchlist_refreshed_at(market: str) -> datetime | None:
    record = WatchlistMetaRecord.get_or_none(WatchlistMetaRecord.market == market)
    if not record or not record.refreshed_at:
        return None
    return _to_utc(record.refreshed_at)


def _to_float(value: Decimal | float | int) -> float:
    return float(value)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _portfolio_id(market: str) -> int:
    return {"US": 1, "INDIA": 2}.get(market.upper(), 99)


def _scoped_ticker(market: str, ticker: str) -> str:
    return f"{market.upper()}::{ticker}"


def _unscoped_ticker(market: str, ticker: str) -> str:
    prefix = f"{market.upper()}::"
    if ticker.startswith(prefix):
        return ticker[len(prefix) :]
    return ticker


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
    try:
        database.execute_sql(
            """
            ALTER TABLE trades
            ADD COLUMN market VARCHAR(16) NOT NULL DEFAULT 'US'
            """
        )
    except Exception:
        pass
    try:
        database.execute_sql(
            """
            ALTER TABLE positions
            ADD COLUMN market VARCHAR(16) NOT NULL DEFAULT 'US'
            """
        )
    except Exception:
        pass
    try:
        database.execute_sql(
            """
            ALTER TABLE portfolio
            ADD COLUMN market VARCHAR(16) NOT NULL DEFAULT 'US'
            """
        )
    except Exception:
        pass
    try:
        database.execute_sql(
            """
            ALTER TABLE portfolio
            ADD COLUMN session_started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            """
        )
    except Exception:
        pass
    try:
        database.execute_sql(
            """
            ALTER TABLE portfolio
            ADD COLUMN last_settlement_date DATE NULL
            """
        )
    except Exception:
        pass
    try:
        database.execute_sql(
            """
            ALTER TABLE pnl_snapshots
            ADD COLUMN market VARCHAR(16) NOT NULL DEFAULT 'US'
            """
        )
    except Exception:
        pass
    try:
        database.execute_sql(
            """
            ALTER TABLE daily_investments
            ADD COLUMN market VARCHAR(16) NOT NULL DEFAULT 'US'
            """
        )
    except Exception:
        pass
    try:
        database.execute_sql(
            """
            CREATE UNIQUE INDEX daily_investments_market_session_date
            ON daily_investments (market, session_date)
            """
        )
    except Exception:
        pass
    try:
        database.execute_sql(
            """
            CREATE UNIQUE INDEX watchlists_market_ticker
            ON watchlists (market, ticker)
            """
        )
    except Exception:
        pass
    try:
        database.execute_sql(
            """
            DROP INDEX session_date ON daily_investments
            """
        )
    except Exception:
        pass
