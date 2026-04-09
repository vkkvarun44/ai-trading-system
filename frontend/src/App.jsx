import { useCallback, useState } from "react";
import { Route, Routes, useLocation } from "react-router-dom";

import { Layout } from "./components/Layout";
import { DashboardPage } from "./pages/DashboardPage";
import { PnLPage } from "./pages/PnLPage";
import { PortfolioPage } from "./pages/PortfolioPage";
import { TradesPage } from "./pages/TradesPage";
import { WatchlistPage } from "./pages/WatchlistPage";
import { usePolling } from "./hooks/usePolling";
import { api } from "./services/api";

const EMPTY_MOVERS = { gainers: [], losers: [] };
const EMPTY_SIGNALS = [];
const EMPTY_PNL = { current: null, history: [] };
const EMPTY_TRADES = [];
const EMPTY_WATCHLIST = { tickers: [], count: 0, last_refreshed_at: null, refresh_interval_seconds: 60 };

function ErrorBanner({ message }) {
  if (!message) {
    return null;
  }

  return (
    <div className="mb-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
      {message}
    </div>
  );
}

export default function App() {
  const [refreshKey, setRefreshKey] = useState(0);
  const [switchingMarket, setSwitchingMarket] = useState(false);
  const location = useLocation();
  const isDashboardPage = location.pathname === "/";
  const isPortfolioPage = location.pathname.startsWith("/portfolio");
  const isTradesPage = location.pathname.startsWith("/trades");
  const isPnlPage = location.pathname.startsWith("/pnl");
  const isWatchlistPage = location.pathname.startsWith("/watchlist");

  const getMarketStatus = useCallback(() => api.getMarketStatus(), [refreshKey]);
  const getTopMovers = useCallback(() => api.getTopMovers(), [refreshKey]);
  const getSignals = useCallback(() => api.getSignals(), [refreshKey]);
  const getPortfolio = useCallback(() => api.getPortfolio(), [refreshKey]);
  const getPnL = useCallback(() => api.getPnL(), [refreshKey]);
  const getTrades = useCallback(() => api.getTrades(), [refreshKey]);

  const marketStatusState = usePolling(getMarketStatus, 60000, null);
  const getWatchlist = useCallback(
    () => api.getWatchlist(marketStatusState.data?.active_market),
    [refreshKey, marketStatusState.data?.active_market]
  );
  const isMarketOpen = marketStatusState.data?.is_open ?? false;
  const moversState = usePolling(getTopMovers, 10000, EMPTY_MOVERS, {
    enabled: isMarketOpen && isDashboardPage,
    resetOnDisable: true
  });
  const signalsState = usePolling(getSignals, 8000, EMPTY_SIGNALS, {
    enabled: isMarketOpen && isDashboardPage,
    resetOnDisable: true
  });
  const portfolioState = usePolling(getPortfolio, 12000, null, {
    enabled: isDashboardPage || isPortfolioPage
  });
  const pnlState = usePolling(getPnL, 8000, EMPTY_PNL, {
    enabled: isPnlPage,
    resetOnDisable: true
  });
  const tradesState = usePolling(getTrades, 8000, EMPTY_TRADES, {
    enabled: isTradesPage,
    resetOnDisable: true
  });
  const watchlistState = usePolling(getWatchlist, 30000, EMPTY_WATCHLIST, {
    enabled: isWatchlistPage,
    resetOnDisable: false
  });

  async function handleMarketChange(nextMarket) {
    if (!marketStatusState.data || marketStatusState.data.active_market === nextMarket) {
      return;
    }

    setSwitchingMarket(true);
    try {
      const nextStatus = await api.setActiveMarket(nextMarket);
      marketStatusState.setData(nextStatus);
      setRefreshKey((current) => current + 1);
    } finally {
      setSwitchingMarket(false);
    }
  }

  const errorMessage = [
    marketStatusState.error,
    moversState.error,
    signalsState.error,
    portfolioState.error,
    pnlState.error,
    tradesState.error,
    watchlistState.error
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <Layout
      marketStatus={marketStatusState.data}
      onMarketChange={handleMarketChange}
      switchingMarket={switchingMarket}
    >
      <ErrorBanner message={errorMessage} />
      <Routes>
        <Route
          path="/"
          element={
            <DashboardPage
              movers={moversState.data}
              signals={signalsState.data}
              portfolio={portfolioState.data}
              marketStatus={marketStatusState.data}
            />
          }
        />
        <Route
          path="/watchlist"
          element={<WatchlistPage watchlist={watchlistState.data} marketStatus={marketStatusState.data} />}
        />
        <Route
          path="/portfolio"
          element={<PortfolioPage portfolio={portfolioState.data} marketStatus={marketStatusState.data} />}
        />
        <Route
          path="/trades"
          element={<TradesPage trades={tradesState.data} marketStatus={marketStatusState.data} />}
        />
        <Route path="/pnl" element={<PnLPage pnl={pnlState.data} marketStatus={marketStatusState.data} />} />
      </Routes>
    </Layout>
  );
}
