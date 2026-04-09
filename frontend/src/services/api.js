const API_BASE_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed for ${path}`);
  }

  return response.json();
}

export const api = {
  getMarketStatus: () => request("/market-status"),
  setActiveMarket: (market) =>
    request("/market-status", {
      method: "PUT",
      body: JSON.stringify({ market })
    }),
  getTopMovers: () => request("/top-movers"),
  getWatchlist: (market) => request(market ? `/watchlist?market=${encodeURIComponent(market)}` : "/watchlist"),
  getSignals: () => request("/signals"),
  getPortfolio: () => request("/portfolio"),
  getPnL: () => request("/pnl"),
  getTrades: () => request("/trades")
};
