import { DataTable } from "../components/DataTable";
import { StatCard } from "../components/StatCard";

function formatDateTime(value, timezone) {
  if (!value) {
    return "Not refreshed yet";
  }

  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone
  }).format(new Date(value));
}

export function WatchlistPage({ watchlist, marketStatus }) {
  const rows = (watchlist?.tickers || []).map((ticker, index) => ({
    id: `${ticker}-${index}`,
    position: index + 1,
    ticker
  }));

  const columns = [
    { key: "position", label: "#" },
    { key: "ticker", label: "Ticker" }
  ];

  return (
    <div className="space-y-8">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <StatCard label="Watchlist Size" value={String(watchlist?.count || 0)} accent="amber" />
        <StatCard
          label="Refresh Cadence"
          value={`${Math.round((watchlist?.refresh_interval_seconds || 60) / 60)} min`}
          accent="slate"
        />
        <StatCard
          label="Last Refresh"
          value={formatDateTime(watchlist?.last_refreshed_at, marketStatus?.timezone)}
          accent="green"
        />
      </section>

      <section className="space-y-3">
        <div>
          <h2 className="font-display text-2xl text-ink">Active Watchlist</h2>
          <p className="text-sm text-slate-500">
            The backend refreshes this list every 15 minutes during market hours and keeps the last
            generated list visible after the market closes.
          </p>
        </div>
        <DataTable
          columns={columns}
          rows={rows}
          emptyMessage="The watchlist has not been generated yet."
          maxHeightClass="max-h-[34rem]"
        />
      </section>
    </div>
  );
}
