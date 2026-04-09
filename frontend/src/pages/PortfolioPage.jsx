import { DataTable } from "../components/DataTable";
import { SignalBadge } from "../components/SignalBadge";
import { StatCard } from "../components/StatCard";
import { formatCurrency } from "../utils/formatters";

export function PortfolioPage({ portfolio, marketStatus }) {
  const currencyCode = marketStatus?.currency_code || "USD";
  const currencyLocale = marketStatus?.currency_locale || "en-US";
  const columns = [
    { key: "ticker", label: "Ticker" },
    { key: "side", label: "Position" },
    { key: "last_action", label: "Latest Action", render: (value) => <SignalBadge value={value} /> },
    { key: "qty", label: "Qty" },
    { key: "avg_price", label: "Avg Price", render: (value) => formatCurrency(value, currencyCode, currencyLocale) },
    { key: "market_price", label: "Market Price", render: (value) => formatCurrency(value, currencyCode, currencyLocale) },
    { key: "market_value", label: "Market Value", render: (value) => formatCurrency(value, currencyCode, currencyLocale) },
    { key: "unrealized_pnl", label: "Unrealized PnL", render: (value) => formatCurrency(value, currencyCode, currencyLocale) },
    { key: "realized_pnl", label: "Realized PnL", render: (value) => formatCurrency(value, currencyCode, currencyLocale) }
  ];

  return (
    <div className="space-y-8">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total Value" value={formatCurrency(portfolio?.total_value, currencyCode, currencyLocale)} accent="amber" />
        <StatCard label="Cash" value={formatCurrency(portfolio?.cash, currencyCode, currencyLocale)} accent="slate" />
        <StatCard label="Invested Cost" value={formatCurrency(portfolio?.invested_value, currencyCode, currencyLocale)} accent="green" />
        <StatCard label="Trades" value={String(portfolio?.trade_count || 0)} accent="red" />
      </section>
      <section className="space-y-3">
        <div>
          <h2 className="font-display text-2xl text-ink">Open Positions</h2>
          <p className="text-sm text-slate-500">Real-time valuation is refreshed with the polling cycle.</p>
        </div>
        <DataTable columns={columns} rows={portfolio?.positions || []} emptyMessage="No open positions yet." />
      </section>
    </div>
  );
}
