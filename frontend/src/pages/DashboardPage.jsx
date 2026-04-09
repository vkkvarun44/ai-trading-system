import { DataTable } from "../components/DataTable";
import { SignalBadge } from "../components/SignalBadge";
import { StatCard } from "../components/StatCard";
import { formatCurrency } from "../utils/formatters";

function formatPercent(value) {
  return `${(value || 0).toFixed(2)}%`;
}

export function DashboardPage({ movers, signals, portfolio, marketStatus }) {
  const currencyCode = marketStatus?.currency_code || "USD";
  const currencyLocale = marketStatus?.currency_locale || "en-US";
  const signalColumns = [
    { key: "ticker", label: "Ticker" },
    { key: "signal", label: "Signal", render: (value) => <SignalBadge value={value} /> },
    { key: "price", label: "Price", render: (value) => formatCurrency(value, currencyCode, currencyLocale) },
    { key: "change_pct", label: "Change", render: (value) => formatPercent(value) },
    { key: "rsi", label: "RSI", render: (value) => value.toFixed(2) },
    { key: "ema_9", label: "EMA 9", render: (value) => formatCurrency(value, currencyCode, currencyLocale) },
    { key: "ema_21", label: "EMA 21", render: (value) => formatCurrency(value, currencyCode, currencyLocale) }
  ];

  const moverColumns = [
    { key: "ticker", label: "Ticker" },
    { key: "price", label: "Price", render: (value) => formatCurrency(value, currencyCode, currencyLocale) },
    { key: "change_pct", label: "Change", render: (value) => formatPercent(value) }
  ];

  return (
    <div className="space-y-8">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Cash Balance" value={formatCurrency(portfolio?.cash, currencyCode, currencyLocale)} accent="amber" />
        <StatCard label="Market Value" value={formatCurrency(portfolio?.market_value, currencyCode, currencyLocale)} accent="slate" />
        <StatCard label="Unrealized PnL" value={formatCurrency(portfolio?.unrealized_pnl, currencyCode, currencyLocale)} accent="green" />
        <StatCard label="Realized PnL" value={formatCurrency(portfolio?.realized_pnl, currencyCode, currencyLocale)} accent="red" />
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <div className="space-y-3">
          <div>
            <h2 className="font-display text-2xl text-ink">Top Gainers</h2>
            <p className="text-sm text-slate-500">Highest relative strength across the watchlist.</p>
          </div>
          <DataTable
            columns={moverColumns}
            rows={movers?.gainers || []}
            emptyMessage="No gainers found."
            maxHeightClass="max-h-[24rem]"
          />
        </div>
        <div className="space-y-3">
          <div>
            <h2 className="font-display text-2xl text-ink">Top Losers</h2>
            <p className="text-sm text-slate-500">Potential mean-reversion or continuation candidates.</p>
          </div>
          <DataTable
            columns={moverColumns}
            rows={movers?.losers || []}
            emptyMessage="No losers found."
            maxHeightClass="max-h-[24rem]"
          />
        </div>
      </section>

      <section className="space-y-3">
        <div>
          <h2 className="font-display text-2xl text-ink">Latest Signals</h2>
          <p className="text-sm text-slate-500">Signals are refreshed from the backend polling cycle.</p>
        </div>
        <DataTable
          columns={signalColumns}
          rows={signals || []}
          emptyMessage="Signals will appear here after the first refresh."
          maxHeightClass="max-h-[30rem]"
        />
      </section>
    </div>
  );
}
