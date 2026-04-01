"""Portfolio and trade history routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.dependencies import paper_engine, state
from db.models import PnLResponseModel, PortfolioModel, TradeModel
from market.yahoo_scanner import get_latest_prices

router = APIRouter(tags=["trading"])


@router.get("/portfolio", response_model=PortfolioModel)
def get_portfolio() -> PortfolioModel:
    tickers = [position.ticker for position in paper_engine.get_portfolio().positions]
    prices = get_latest_prices(tickers)
    return paper_engine.get_portfolio(prices)


@router.get("/pnl", response_model=PnLResponseModel)
def get_pnl() -> PnLResponseModel:
    tickers = [position.ticker for position in paper_engine.get_portfolio().positions]
    prices = get_latest_prices(tickers)
    return paper_engine.calculate_pnl(prices)


@router.get("/trades", response_model=list[TradeModel])
def get_trades() -> list[TradeModel]:
    return state.get_trades()
