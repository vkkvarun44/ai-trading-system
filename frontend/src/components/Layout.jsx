import { NavLink } from "react-router-dom";

const navItems = [
  { to: "/", label: "Dashboard" },
  { to: "/watchlist", label: "Watchlist" },
  { to: "/portfolio", label: "Portfolio" },
  { to: "/trades", label: "Trades" },
  { to: "/pnl", label: "PnL View" }
];

export function Layout({ children, marketStatus, onMarketChange, switchingMarket = false }) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-amber-200/60 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-6 py-6 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="font-display text-3xl text-ink">Atlas Paper Trader</p>
            <p className="mt-1 text-sm text-slate-500">
              Automated AI signal execution and portfolio telemetry in one place.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {marketStatus ? (
              <>
                <label className="flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">
                  <span className="font-semibold">Market</span>
                  <select
                    className="bg-transparent outline-none"
                    value={marketStatus.active_market}
                    onChange={(event) => onMarketChange?.(event.target.value)}
                    disabled={switchingMarket}
                  >
                    <option value="US">US</option>
                    <option value="INDIA">INDIA</option>
                  </select>
                </label>
                <div
                  className={`rounded-full border px-4 py-2 text-sm font-semibold ${
                    marketStatus.is_open
                      ? "border-green-200 bg-green-50 text-green-800"
                      : "border-slate-200 bg-slate-100 text-slate-700"
                  }`}
                >
                  {marketStatus.market_name} {marketStatus.status}
                </div>
              </>
            ) : null}
            <nav className="flex flex-wrap gap-2 rounded-full bg-slate-900 p-1 shadow-panel">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  className={({ isActive }) =>
                    `rounded-full px-4 py-2 text-sm transition ${
                      isActive ? "bg-amber-300 text-slate-900" : "text-slate-300 hover:text-white"
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
    </div>
  );
}
