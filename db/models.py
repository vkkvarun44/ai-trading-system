"""Shared Pydantic models used by the API and execution engine."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


SignalValue = Literal["BUY", "SELL", "HOLD", "AVOID"]
OrderSide = Literal["BUY", "SELL"]
TradeStatus = Literal["FILLED", "REJECTED", "SKIPPED"]
PositionSide = Literal["LONG", "SHORT"]


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


class DashboardResponse(BaseModel):
    gainers: list[MarketMover]
    losers: list[MarketMover]
    signals: list[SignalModel]
    portfolio: PortfolioModel
    pnl: PnLResponseModel
