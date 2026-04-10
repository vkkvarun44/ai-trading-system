"""Shared Pydantic models used by the API and execution engine."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


SignalValue = Literal["BUY", "SELL", "HOLD", "AVOID", "SHORT"]
OrderSide = Literal["BUY", "SELL"]
TradeStatus = Literal["FILLED", "REJECTED", "SKIPPED"]
PositionSide = Literal["LONG", "SHORT"]
MarketKey = Literal["US", "INDIA"]


class MarketMover(BaseModel):
    ticker: str
    price: float
    change_pct: float


class SignalModel(BaseModel):
    ticker: str
    signal: SignalValue
    price: float
    rsi: float
    ema_9: float
    ema_21: float
    ema_50: float = 0.0
    ema_200: float = 0.0
    macd: float = 0.0
    macd_signal: float = 0.0
    atr: float = 0.0
    adx: float = 0.0
    volume_ratio: float = 0.0
    trend_strength: float = 0.0
    regime: str = "SIDEWAYS"
    regime_confidence: float = 0.0
    strategy_direction: str = "both"
    strategy_reward_ratio: float = 0.0
    position_size_multiplier: float = 1.0
    stop_loss: float = 0.0
    target_price: float = 0.0
    rejection_reason: str | None = None
    change_pct: float
    generated_at: datetime


class PositionModel(BaseModel):
    ticker: str
    qty: int
    avg_price: float
    side: PositionSide = "LONG"
    last_action: OrderSide = "BUY"
    market_price: float = 0.0
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    last_updated: datetime


class TradeModel(BaseModel):
    trade_id: str
    ticker: str
    side: OrderSide
    qty: int
    price: float
    value: float
    status: TradeStatus
    reason: str
    signal: str
    timestamp: datetime
    realized_pnl: float = 0.0


class PortfolioModel(BaseModel):
    initial_capital: float
    cash: float
    invested_value: float
    market_value: float
    total_value: float
    realized_pnl: float
    unrealized_pnl: float
    positions: list[PositionModel]
    trade_count: int
    updated_at: datetime


class PnLSnapshotModel(BaseModel):
    timestamp: datetime
    total_value: float
    cash: float
    market_value: float
    realized_pnl: float
    unrealized_pnl: float


class PnLResponseModel(BaseModel):
    current: PnLSnapshotModel
    history: list[PnLSnapshotModel]


class DailyInvestmentRecordModel(BaseModel):
    session_date: date
    starting_capital: float
    closing_cash: float
    closing_market_value: float
    ending_capital: float
    realized_pnl: float
    unrealized_pnl: float
    net_pnl: float
    positions_closed: int
    settled_at: datetime


class DashboardResponse(BaseModel):
    gainers: list[MarketMover]
    losers: list[MarketMover]
    signals: list[SignalModel]
    portfolio: PortfolioModel
    pnl: PnLResponseModel


class MarketStatusModel(BaseModel):
    active_market: MarketKey
    market_name: str
    status: str
    is_open: bool
    timezone: str
    current_time: str
    next_open: str
    market_open_time: str
    market_close_time: str
    currency_code: str
    currency_locale: str
    watchlist_size: int


class MarketSelectionRequestModel(BaseModel):
    market: MarketKey


class WatchlistPrepareRequestModel(BaseModel):
    market: MarketKey
    tickers: list[str]


class WatchlistUpdateRequestModel(BaseModel):
    market: MarketKey
    tickers: list[str]


class WatchlistResponseModel(BaseModel):
    market: MarketKey
    tickers: list[str]
    count: int
    last_refreshed_at: datetime | None = None
    refresh_interval_seconds: int | None = None


class WatchlistPreparationResultModel(BaseModel):
    market: MarketKey
    input_count: int
    prepared_count: int
    tickers: list[str]
    invalid_tickers: list[str]


class AutoWatchlistRequestModel(BaseModel):
    market: MarketKey
    target_size: int | None = None


class AutoWatchlistCandidateModel(BaseModel):
    ticker: str
    price: float
    change_pct: float
    avg_volume: float
    score: float
    trend_strength: float = 0.0
    volume_ratio: float = 0.0
    volatility_expansion: float = 0.0
    regime: str = ""
    confidence: float = 0.0
    rejection_reason: str | None = None


class AutoWatchlistResponseModel(BaseModel):
    market: MarketKey
    universe_size: int
    eligible_count: int
    target_size: int
    tickers: list[str]
    candidates: list[AutoWatchlistCandidateModel]
