# AI Trading System

An intraday AI-assisted paper trading framework for scanning stocks, generating adaptive signals, executing simulated trades, tracking portfolio performance, and evaluating strategy behavior through backtesting and feedback analytics.

The system is built around a shared trading pipeline so live paper trading and backtesting use the same core logic:

```text
OHLCV data -> indicators -> features -> market regime -> stock ranking -> strategy params -> risk checks -> execution/backtest
```

## What This Project Does

- Fetches U.S. and India market data with Yahoo Finance and NSE-backed universe builders.
- Maintains configurable and auto-built watchlists.
- Calculates technical indicators with the `ta` library.
- Detects market regimes with an XGBoost classifier.
- Dynamically adjusts strategy behavior by regime.
- Ranks candidate stocks by confidence, trend strength, and volume strength.
- Executes trades in a paper broker with cash, positions, stop-loss, targets, and PnL tracking.
- Runs an automated intraday trading cycle while respecting market hours.
- Closes positions before market close to avoid overnight exposure.
- Stores portfolio state, trades, PnL snapshots, daily settlement records, and watchlists in MySQL when persistence is enabled.
- Provides a FastAPI backend and a React dashboard.
- Includes a backtesting engine that reuses the same regime and strategy logic as live trading.
- Includes a feedback loop to analyze performance by regime and identify weak market conditions.

## Implemented Functionality

### Market Data

- U.S. market movers and watchlist data through Yahoo Finance.
- India universe generation through NSE endpoints.
- Yahoo Finance OHLCV downloads for indicators, latest prices, and auto-watchlist candidate scoring.
- Cache controls for latest prices, top movers, and indicators.

### Indicators

Indicators are calculated with `ta`, not `pandas-ta`.

- RSI
- EMA 9 and EMA 21 for dashboard/signal context
- EMA 50 and EMA 200 for trend structure
- MACD and MACD signal
- ADX
- ATR
- Average volume and volume ratio

### Feature Engineering

The regime model uses:

- `rsi`
- `adx`
- `atr`
- `ema_50_slope`
- `ema_200_slope`
- `volatility`
- `volume_ratio`
- `trend_strength`

`trend_strength` is calculated as:

```python
df["trend_strength"] = df["ema_50"] - df["ema_200"]
```

### Market Regime Detection

The system labels and predicts four regimes:

- `TRENDING_UP`
- `TRENDING_DOWN`
- `SIDEWAYS`
- `HIGH_VOLATILITY`

The current ML model is `XGBClassifier` with:

- `n_estimators=200`
- `max_depth=6`
- `learning_rate=0.05`
- Multi-class soft probability output
- Time-series-safe train/test split with no shuffling
- Validation `eval_set`
- Accuracy and classification report output

### Dynamic Strategy Adjustment

Strategy parameters are selected by detected regime:

- `TRENDING_UP`: long-only, stronger RSI confirmation, higher reward ratio.
- `TRENDING_DOWN`: short-only, stronger downside confirmation, higher reward ratio.
- `SIDEWAYS`: both directions, mean-reversion style RSI thresholds, lower reward ratio.
- `HIGH_VOLATILITY`: both directions, reduced position size, higher confidence requirement.

The live and backtest paths share these helpers:

- `predict_regime`
- `predict_with_confidence`
- `get_strategy_params`
- `evaluate_strategy_signal`
- `calculate_atr_levels`

### Stock Ranking

The stock ranking layer selects the top 3 stocks using model confidence, trend strength, and volume strength:

```python
score = (confidence * 0.5) + (trend_strength * 0.3) + (volume_ratio * 0.2)
```

This helps avoid taking every valid signal blindly and pushes better candidates to the front of the pipeline.

### Paper Trading

The paper trading engine supports:

- Simulated `BUY` and `SELL` orders
- Long and short position tracking
- Cash balance updates
- Average price tracking
- Realized and unrealized PnL
- Stop-loss and target-price storage
- Trade statuses: `FILLED`, `REJECTED`, `SKIPPED`
- Cooldown protection to prevent duplicate rapid-fire trades
- End-of-day position flattening

### Risk Management

Implemented risk controls:

- ATR-based stop-loss
- ATR-based target using regime-specific reward ratio
- Risk-based position sizing
- Max position size cap
- Regime confidence filter
- Regime direction filter
- Daily loss kill switch using `DAILY_LOSS_LIMIT_PCT`

The daily trade-count limit was removed from live validation so trades are no longer rejected with `Daily trade limit reached`.

### Backtesting

Backtesting lives in:

```text
backtesting/engine.py
```

`run_backtest(df, model)`:

- Builds indicators and features from historical OHLCV data.
- Predicts regime per candle.
- Applies shared strategy logic.
- Simulates entries and exits.
- Uses ATR stop-loss and regime reward-ratio targets.
- Tracks balance and equity curve.
- Squares off open positions at session changes and final candle.
- Applies daily loss kill switch.

Backtest output includes:

- Total trades
- Win rate
- Total profit
- Max drawdown
- Profit factor
- Ending balance
- Equity curve
- Trade log
- Performance summary by regime

### Feedback Learning Loop

Trade logs can be analyzed with:

```python
analyze_performance(trade_logs)
```

Expected trade log shape:

```python
{
    "stock": "RELIANCE.NS",
    "regime": "TRENDING_UP",
    "confidence": 0.74,
    "profit": 1250.50,
}
```

Output includes:

- Profit by regime
- Win rate by regime
- Average profit per trade
- Weak regimes
- Disabled regime candidates

This is the foundation for turning off regimes that consistently lose money.

### Watchlists

The system supports:

- Configured fallback watchlists
- Manual watchlist updates through API
- Auto-built watchlists from broader market universes
- Separate U.S. and India watchlists
- Runtime watchlist refresh

Current defaults:

- U.S. fallback watchlist: 61 tickers
- India fallback watchlist: 51 tickers
- Auto-built watchlist target: 50 tickers

If an auto-built or persisted watchlist is shorter than the target, the watchlist manager tops it up from configured defaults without duplicates.

## Project Structure

```text
ai-trading-system/
├── app/
│   ├── main.py
│   ├── dependencies.py
│   ├── routes/
│   │   ├── health.py
│   │   ├── market.py
│   │   ├── signal.py
│   │   └── trades.py
│   └── services/
│       ├── market_hours.py
│       ├── market_profile.py
│       ├── trading_cycle.py
│       └── watchlist_manager.py
├── backtesting/
│   ├── __init__.py
│   └── engine.py
├── core/
│   ├── config.py
│   └── logger.py
├── db/
│   ├── models.py
│   ├── mysql.py
│   └── persistence.py
├── execution/
│   ├── paper_trader.py
│   ├── risk_management.py
│   └── signal_executor.py
├── markets/
│   ├── nse_universe.py
│   ├── yahoo_scanner.py
│   ├── yahoo_universe.py
│   └── market_universe.py
├── signals/
│   ├── filter_pipeline.py
│   ├── indicator.py
│   ├── market_regime.py
│   ├── signal_engine.py
│   └── strategies/
├── state/
│   └── store.py
├── frontend/
│   ├── package.json
│   └── src/
├── scripts/
│   └── reset_paper_data.py
└── requirements.txt
```

## Backend API

### Health

- `GET /health`

### Market And Watchlist

- `GET /market-status`
- `PUT /market-status`
- `GET /top-movers`
- `GET /watchlist`
- `POST /watchlist/prepare`
- `PUT /watchlist`
- `POST /watchlist/auto-build`
- `PUT /watchlist/auto-build`

### Signals And Trading

- `GET /signals`

### Portfolio And History

- `GET /portfolio`
- `GET /pnl`
- `GET /trades`

OpenAPI docs are available at:

```text
http://127.0.0.1:8000/docs
```

## Requirements

Python dependencies are listed in:

```text
requirements.txt
```

Main backend packages:

- FastAPI
- Uvicorn
- Pydantic
- python-dotenv
- pandas
- yfinance
- requests
- beautifulsoup4
- ta
- scikit-learn
- XGBoost
- Peewee
- PyMySQL

On macOS, XGBoost may require OpenMP:

```bash
brew install libomp
```

## Backend Setup

Create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` file if you want to override defaults:

```env
INITIAL_CAPITAL=100000
POSITION_SIZE_PCT=0.10
FIXED_POSITION_SIZE=0
SIGNAL_COOLDOWN_SECONDS=300
AUTO_EXECUTE_ENABLED=true
AUTO_EXECUTE_ONLY_WHEN_MARKET_OPEN=true
AUTO_EXECUTE_INTERVAL_SECONDS=60
END_OF_DAY_EXIT_BUFFER_MINUTES=15
ACTIVE_MARKET=INDIA
PERSISTENCE_ENABLED=true
PNL_HISTORY_LIMIT=500

MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DATABASE=stock_trades

YAHOO_TIMEOUT_SECONDS=20
YAHOO_RETRY_COUNT=2
YAHOO_BATCH_SIZE=10
YAHOO_RATE_LIMIT_COOLDOWN_SECONDS=180

TOP_MOVERS_CACHE_SECONDS=30
LATEST_PRICES_CACHE_SECONDS=15
INDICATORS_CACHE_SECONDS=300
SIGNAL_TOP_MOVERS_LIMIT=100

AUTO_WATCHLIST_TARGET_SIZE=50
AUTO_WATCHLIST_MIN_PRICE=10
AUTO_WATCHLIST_MIN_AVG_VOLUME=200000
AUTO_WATCHLIST_REFRESH_SECONDS=60

STOP_LOSS_PCT=0.05
TAKE_PROFIT_PCT=0.05
MAX_RISK_PER_TRADE=0.01
DAILY_LOSS_LIMIT_PCT=0.03
REWARD_RATIO=2.0
MAX_POSITION_SIZE=500
MIN_VOLUME_RATIO=1.5
MIN_ATR=0.5
MIN_ADX=20
RSI_BUY_THRESHOLD=55
RSI_SELL_THRESHOLD=45
ATR_STOP_LOSS_MULTIPLIER=1.5
ATR_TARGET_MULTIPLIER=3.0

CORS_ORIGINS=http://localhost:5173
```

Start the backend:

```bash
uvicorn app.main:app --reload
```

Backend URL:

```text
http://127.0.0.1:8000
```

## Frontend Setup

Install frontend dependencies:

```bash
cd frontend
npm install
```

Start the React dashboard:

```bash
npm run dev
```

Frontend URL:

```text
http://127.0.0.1:5173
```

## MySQL Setup

Persistence is controlled by:

```env
PERSISTENCE_ENABLED=true
```

The backend uses Peewee and PyMySQL. Tables are created automatically by the persistence layer when the app starts.

Create the database before starting the backend:

```sql
CREATE DATABASE stock_trades;
```

Then set the MySQL connection variables in `.env`.

If you want to run without MySQL:

```env
PERSISTENCE_ENABLED=false
```

## Running A Backtest

Example:

```python
import pandas as pd

from backtesting.engine import run_backtest
from signals.market_regime import prepare_regime_frame, train_model

df = pd.read_csv("historical_intraday_ohlcv.csv", parse_dates=["Datetime"], index_col="Datetime")

training_frame = prepare_regime_frame(df)
model = train_model(training_frame)

result = run_backtest(df, model)
print(result)
```

Input data should include:

```text
Open, High, Low, Close, Volume
```

Lowercase column names are also supported:

```text
open, high, low, close, volume
```

## Common Workflows

### Check Current Watchlist

```bash
curl "http://127.0.0.1:8000/watchlist?market=INDIA"
```

### Auto-Build And Save Watchlist

```bash
curl -X PUT "http://127.0.0.1:8000/watchlist/auto-build" \
  -H "Content-Type: application/json" \
  -d '{"market":"INDIA","target_size":50}'
```

### Switch Active Market

```bash
curl -X PUT "http://127.0.0.1:8000/market-status" \
  -H "Content-Type: application/json" \
  -d '{"market":"INDIA"}'
```

### Refresh Signals

```bash
curl "http://127.0.0.1:8000/signals"
```

Execution is handled by the automatic trading cycle when `AUTO_EXECUTE_ENABLED=true`.

### Reset Paper Data

```bash
python scripts/reset_paper_data.py --market INDIA
```

Clear saved watchlist too:

```bash
python scripts/reset_paper_data.py --market INDIA --clear-watchlist
```

## How The Live Pipeline Works

1. The active market profile decides whether the system is scanning U.S. or India symbols.
2. The watchlist manager loads a persisted watchlist or builds one from the market universe.
3. The market scanner computes gainers and losers from the watchlist.
4. The signal engine fetches OHLCV candles for each candidate.
5. Indicators are calculated using `ta`.
6. Features are created for regime detection and ranking.
7. The XGBoost regime model predicts the current market regime and confidence.
8. The stock ranking layer can prioritize the strongest candidates.
9. Strategy parameters are selected based on the regime.
10. The filter pipeline accepts or rejects candidates.
11. The execution layer checks cooldowns, duplicate positions, regime confidence, direction, and daily loss kill switch.
12. The paper trader places simulated orders.
13. Portfolio, trades, PnL snapshots, and daily records are persisted when MySQL persistence is enabled.
14. Positions are closed near the end of the trading session to avoid overnight exposure.

## Notes

- This is a paper trading system, not a live broker integration.
- No strategy is guaranteed to be profitable.
- Yahoo Finance and NSE endpoints can rate-limit or return incomplete data.
- The system avoids overnight positions by design.
- A larger watchlist increases scan coverage but also increases data-download time and rate-limit risk.
- Backtesting results depend heavily on data quality, spread/slippage assumptions, and whether your historical candles match live execution conditions.
