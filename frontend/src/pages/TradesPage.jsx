import { DataTable } from "../components/DataTable";
import { SignalBadge } from "../components/SignalBadge";
import { formatCurrency } from "../utils/formatters";

function formatDate(value) {
  return new Date(value).toLocaleString();
}

export function TradesPage({ trades, marketStatus }) {
  const currencyCode = marketStatus?.currency_code || "USD";
  const currencyLocale = marketStatus?.currency_locale || "en-US";
  const visibleTrades = (trades || []).filter((trade) => trade.status !== "SKIPPED");

  const columns = [
    { key: "timestamp", label: "Timestamp", render: (value) => formatDate(value) },
    { key: "ticker", label: "Ticker" },
    { key: "side", label: "Side", render: (value) => <SignalBadge value={value} /> },
    { key: "qty", label: "Qty" },
    { key: "price", label: "Price", render: (value) => formatCurrency(value, currencyCode, currencyLocale) },
    { key: "value", label: "Value", render: (value) => formatCurrency(value, currencyCode, currencyLocale) },
    { key: "status", label: "Status" },
    { key: "reason", label: "Reason" },
    { key: "realized_pnl", label: "Realized PnL", render: (value) => formatCurrency(value, currencyCode, currencyLocale) }
  ];

  return (
    <div className="space-y-3">
      <div>
        <h2 className="font-display text-2xl text-ink">Trade History</h2>
        <p className="text-sm text-slate-500">Shows filled and rejected execution events only.</p>
      </div>
      <DataTable columns={columns} rows={visibleTrades} emptyMessage="No non-skipped trades have been recorded yet." />
    </div>
  );
}
