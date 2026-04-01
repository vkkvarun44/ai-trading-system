"""Application configuration for the paper trading system."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import time


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
    auto_execute_enabled: bool = os.getenv("AUTO_EXECUTE_ENABLED", "true").lower() == "true"
    auto_execute_only_when_market_open: bool = (
        os.getenv("AUTO_EXECUTE_ONLY_WHEN_MARKET_OPEN", "true").lower() == "true"
    )
    auto_execute_interval_seconds: int = int(os.getenv("AUTO_EXECUTE_INTERVAL_SECONDS", "60"))
    market_timezone: str = os.getenv("MARKET_TIMEZONE", "America/New_York")
    market_open_time: time = time.fromisoformat(os.getenv("MARKET_OPEN_TIME", "09:30:00"))
    market_close_time: time = time.fromisoformat(os.getenv("MARKET_CLOSE_TIME", "16:00:00"))
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
    stop_loss_pct: float = float(os.getenv("STOP_LOSS_PCT", "0.05"))
    take_profit_pct: float = float(os.getenv("TAKE_PROFIT_PCT", "0.1"))
    watchlist: list[str] = field(
        default_factory=lambda: [
            ticker.strip()
            for ticker in os.getenv(
                "WATCHLIST",
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


settings = Settings()
