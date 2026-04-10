"""Application configuration for the paper trading system."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import time

from dotenv import load_dotenv


load_dotenv()


@dataclass(slots=True)
class Settings:
    """Runtime configuration loaded from environment variables."""

    app_name: str = "AI Trading Paper Engine"
    api_prefix: str = ""
    cors_origins: list[str] = field(
        default_factory=lambda: [
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
            if origin.strip()
        ]
    )
    initial_capital: float = float(os.getenv("INITIAL_CAPITAL", "100000"))
    position_size_pct: float = float(os.getenv("POSITION_SIZE_PCT", "0.1"))
    fixed_position_size: int = int(os.getenv("FIXED_POSITION_SIZE", "0"))
    signal_cooldown_seconds: int = int(os.getenv("SIGNAL_COOLDOWN_SECONDS", "300"))
    max_trades_per_day: int = int(os.getenv("MAX_TRADES_PER_DAY", "5"))
    auto_execute_enabled: bool = os.getenv("AUTO_EXECUTE_ENABLED", "true").lower() == "true"
    auto_execute_only_when_market_open: bool = (
        os.getenv("AUTO_EXECUTE_ONLY_WHEN_MARKET_OPEN", "true").lower() == "true"
    )
    auto_execute_interval_seconds: int = int(os.getenv("AUTO_EXECUTE_INTERVAL_SECONDS", "60"))
    end_of_day_exit_buffer_minutes: int = int(os.getenv("END_OF_DAY_EXIT_BUFFER_MINUTES", "15"))
    active_market: str = os.getenv("ACTIVE_MARKET", "US").strip().upper()
    persistence_enabled: bool = os.getenv("PERSISTENCE_ENABLED", "true").lower() == "true"
    pnl_history_limit: int = int(os.getenv("PNL_HISTORY_LIMIT", "500"))
    mysql_host: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user: str = os.getenv("MYSQL_USER", "root")
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "")
    mysql_database: str = os.getenv("MYSQL_DATABASE", "stock_trades")
    yahoo_timeout_seconds: int = int(os.getenv("YAHOO_TIMEOUT_SECONDS", "20"))
    yahoo_retry_count: int = int(os.getenv("YAHOO_RETRY_COUNT", "2"))
    yahoo_batch_size: int = int(os.getenv("YAHOO_BATCH_SIZE", "10"))
    yahoo_rate_limit_cooldown_seconds: int = int(os.getenv("YAHOO_RATE_LIMIT_COOLDOWN_SECONDS", "180"))
    top_movers_cache_seconds: int = int(os.getenv("TOP_MOVERS_CACHE_SECONDS", "30"))
    latest_prices_cache_seconds: int = int(os.getenv("LATEST_PRICES_CACHE_SECONDS", "15"))
    indicators_cache_seconds: int = int(os.getenv("INDICATORS_CACHE_SECONDS", "300"))
    signal_top_movers_limit: int = int(os.getenv("SIGNAL_TOP_MOVERS_LIMIT", "100"))
    auto_watchlist_target_size: int = int(os.getenv("AUTO_WATCHLIST_TARGET_SIZE", "50"))
    auto_watchlist_min_price: float = float(os.getenv("AUTO_WATCHLIST_MIN_PRICE", "10"))
    auto_watchlist_min_avg_volume: float = float(os.getenv("AUTO_WATCHLIST_MIN_AVG_VOLUME", "200000"))
    auto_watchlist_refresh_seconds: int = int(os.getenv("AUTO_WATCHLIST_REFRESH_SECONDS", "60"))
    stop_loss_pct: float = float(os.getenv("STOP_LOSS_PCT", "0.05"))
    take_profit_pct: float = float(os.getenv("TAKE_PROFIT_PCT", "0.05"))
    max_risk_per_trade: float = float(os.getenv("MAX_RISK_PER_TRADE", "0.01"))
    daily_loss_limit_pct: float = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "0.03"))
    reward_ratio: float = float(os.getenv("REWARD_RATIO", "2.0"))       # 1:2 RR
    max_position_size: int = int(os.getenv("MAX_POSITION_SIZE", "500")) 
    min_volume_ratio: float = float(os.getenv("MIN_VOLUME_RATIO", "1.5"))
    min_atr: float = float(os.getenv("MIN_ATR", "0.5"))
    min_adx: float = float(os.getenv("MIN_ADX", "20"))
    rsi_buy_threshold: float = float(os.getenv("RSI_BUY_THRESHOLD", "55"))
    rsi_sell_threshold: float = float(os.getenv("RSI_SELL_THRESHOLD", "45"))
    atr_stop_loss_multiplier: float = float(os.getenv("ATR_STOP_LOSS_MULTIPLIER", "1.5"))
    atr_target_multiplier: float = float(os.getenv("ATR_TARGET_MULTIPLIER", "3.0"))
    us_watchlist: list[str] = field(
        default_factory=lambda: [
            ticker.strip()
            for ticker in os.getenv(
                "US_WATCHLIST",
                (
                    "AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AMD,NFLX,INTC,"
                    "CRM,ORCL,UBER,PLTR,SHOP,AVGO,ADBE,QCOM,CSCO,TXN,"
                    "JPM,BAC,WFC,GS,MS,V,MA,PYPL,AXP,BLK,C,"
                    "LLY,UNH,JNJ,MRK,ABBV,PFE,TMO,ISRG,AMGN,GILD,"
                    "XOM,CVX,COP,SLB,CAT,DE,GE,BA,RTX,LMT,"
                    "WMT,COST,HD,LOW,NKE,SBUX,MCD,PEP,KO,DIS"
                ),
            ).split(",")
            if ticker.strip()
        ]
    )
    india_watchlist: list[str] = field(
        default_factory=lambda: [
            ticker.strip()
            for ticker in os.getenv(
                "INDIA_WATCHLIST",
                (
                    "RELIANCE.NS,TCS.NS,HDFCBANK.NS,ICICIBANK.NS,INFY.NS,SBIN.NS,"
                    "BHARTIARTL.NS,ITC.NS,LT.NS,AXISBANK.NS,KOTAKBANK.NS,HINDUNILVR.NS,"
                    "ASIANPAINT.NS,BAJFINANCE.NS,MARUTI.NS,SUNPHARMA.NS,TITAN.NS,"
                    "ULTRACEMCO.NS,WIPRO.NS,POWERGRID.NS,HCLTECH.NS,TECHM.NS,LTIM.NS,"
                    "BAJAJFINSV.NS,HDFCLIFE.NS,SBILIFE.NS,ADANIENT.NS,ADANIPORTS.NS,"
                    "ONGC.NS,NTPC.NS,COALINDIA.NS,BPCL.NS,IOC.NS,TATASTEEL.NS,JSWSTEEL.NS,"
                    "HINDALCO.NS,GRASIM.NS,CIPLA.NS,DRREDDY.NS,DIVISLAB.NS,APOLLOHOSP.NS,"
                    "NESTLEIND.NS,BRITANNIA.NS,TATACONSUM.NS,EICHERMOT.NS,HEROMOTOCO.NS,"
                    "BAJAJ-AUTO.NS,M&M.NS,TATAMOTORS.NS,UPL.NS,SHREECEM.NS"
                ),
            ).split(",")
            if ticker.strip()
        ]
    )
    us_market_source_urls: list[str] = field(
        default_factory=lambda: [
            url.strip()
            for url in os.getenv(
                "US_MARKET_SOURCE_URLS",
                (
                    "https://finance.yahoo.com/most-active,"
                    "https://www.nasdaq.com/market-activity/most-active"
                ),
            ).split(",")
            if url.strip()
        ]
    )

    india_market_source_urls: list[str] = field(
        default_factory=lambda: [
            url.strip()
            for url in os.getenv(
                "INDIA_MARKET_SOURCE_URLS",
                (
                    "https://www.nseindia.com/market-data/most-active-equities,"
                    "https://www.nseindia.com/market-data/most-active-underlying"
                ),
            ).split(",")
            if url.strip()
        ]
    )


settings = Settings()
