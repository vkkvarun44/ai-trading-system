# AI Trading Paper Trading System

This project extends the existing AI trading engine into a production-style paper trading stack with:

- FastAPI backend
- Yahoo Finance market data ingestion
- Signal generation using Momentum + RSI + EMA
- Paper trading engine with portfolio tracking, trade history, cooldown rules, and PnL snapshots
- MySQL persistence for trades, positions, and portfolio state
- React + Tailwind dashboard with polling-based real-time updates

## Folder Structure

```text
ai-trading-system/
├── app/
│   ├── dependencies.py
│   ├── main.py
│   └── routes/
│       ├── health.py
│       ├── market.py
│       ├── signal.py
│       └── trades.py
├── core/
│   ├── config.py
│   └── logger.py
├── db/
│   ├── models.py
│   ├── mysql.py
│   └── persistence.py
├── execution/
│   ├── paper_trader.py
│   └── signal_executor.py
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── pages/
│   │   └── services/api.js
│   └── tailwind.config.js
├── market/
│   └── yahoo_scanner.py
├── signals/
│   ├── indicator.py
│   ├── signal_engine.py
│   └── strategies/
│       └── momentum_rsi.py
├── state/
│   └── store.py
└── requirements.txt
```

## Backend Features

- Initial paper capital of `100000`
- Simulated `BUY` and `SELL` order execution
- Cash, position, and average price tracking
- Realized and unrealized PnL calculation
- Trade ledger with `FILLED`, `REJECTED`, and `SKIPPED` outcomes
- Cooldown protection to avoid duplicate rapid-fire trades
- Position sizing using fixed quantity or percentage of capital
- Optional stop-loss and take-profit exits
- Automatic scheduled execution loop for hands-free paper trading
- MySQL-backed persistence for trades, positions, and equity history

## API Endpoints

- `GET /health`
- `GET /top-movers`
- `GET /signals`
- `GET /portfolio`
- `GET /pnl`
- `GET /trades`

## Backend Setup

1. Create or activate your virtual environment.
2. Install Python dependencies:

```bash
pip install -r requirements.txt
```

3. Optionally create a `.env` file from the example values below.
4. Start the FastAPI server:

```bash
uvicorn app.main:app --reload
```

5. Open the API docs:

```text
http://127.0.0.1:8000/docs
```

## Frontend Setup

1. Move into the frontend app:

```bash
cd frontend
```

2. Install frontend dependencies:

```bash
npm install
```

3. Start the React dashboard:

```bash
npm run dev
```

4. Open the frontend:

```text
http://127.0.0.1:5173
```

## Environment Variables

You can configure the backend with the following variables:

```env
INITIAL_CAPITAL=100000
POSITION_SIZE_PCT=0.10
FIXED_POSITION_SIZE=0
SIGNAL_COOLDOWN_SECONDS=300
AUTO_EXECUTE_ENABLED=true
AUTO_EXECUTE_ONLY_WHEN_MARKET_OPEN=true
AUTO_EXECUTE_INTERVAL_SECONDS=60
MARKET_TIMEZONE=America/New_York
MARKET_OPEN_TIME=09:30:00
MARKET_CLOSE_TIME=16:00:00
PERSISTENCE_ENABLED=true
PNL_HISTORY_LIMIT=500
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DATABASE=stock_trades
TOP_MOVERS_LIMIT=100
STOP_LOSS_PCT=0.05
TAKE_PROFIT_PCT=0.10
CORS_ORIGINS=http://localhost:5173
WATCHLIST=AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AMD,NFLX,INTC,CRM,ORCL,UBER,PLTR,SHOP,AVGO,ADBE,QCOM,CSCO,TXN,JPM,BAC,WFC,GS,MS,V,MA,PYPL,AXP,BLK,C,LLY,UNH,JNJ,MRK,ABBV,PFE,TMO,ISRG,AMGN,GILD,XOM,CVX,COP,SLB,CAT,DE,GE,BA,RTX,LMT,WMT,COST,HD,LOW,NKE,SBUX,MCD,PEP,KO,DIS
```

## How It Works End-to-End

1. `GET /signals` computes top movers from the configured watchlist.
2. The signal engine calculates RSI and EMAs for each candidate ticker.
3. Strategy output produces `BUY`, `SELL`, `HOLD`, or `AVOID`.
4. A background scheduler runs the execution pipeline every `AUTO_EXECUTE_INTERVAL_SECONDS`.
5. When `AUTO_EXECUTE_ONLY_WHEN_MARKET_OPEN=true`, it only runs during regular U.S. market hours of `09:30` to `16:00` in `America/New_York`.
6. The execution engine applies cooldown checks for entries and forces stop-loss/take-profit exits when needed.
7. The paper broker updates cash, positions, trade history, and realized PnL.
8. Portfolio state, trades, and PnL snapshots are persisted into MySQL.
9. `GET /portfolio` and `GET /pnl` value the portfolio using latest Yahoo Finance prices.
10. The React dashboard polls the backend every 8-10 seconds and updates the dashboard, portfolio, trades, and PnL chart.

## Notes

- State is currently stored in memory for paper trading simplicity.
- With persistence enabled, restarting the backend reloads trades, positions, cash, and PnL history from MySQL.
- To disable hands-free trading, set `AUTO_EXECUTE_ENABLED=false`.
- Market-hours gating currently uses regular weekday hours and does not yet exclude exchange holidays.
