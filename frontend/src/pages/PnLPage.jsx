import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { StatCard } from "../components/StatCard";
import { formatCurrency, formatCurrencyAxis } from "../utils/formatters";

function formatDate(value) {
  return new Date(value).toLocaleTimeString();
}

function buildYAxisDomain(history, fallbackValue) {
  const values = history
    .map((point) => point?.total_value)
    .filter((value) => typeof value === "number" && Number.isFinite(value));

  if (values.length === 0 && typeof fallbackValue === "number") {
    const padding = Math.max(Math.abs(fallbackValue) * 0.005, 1);
    return [fallbackValue - padding, fallbackValue + padding];
  }

  if (values.length === 0) {
    return ["auto", "auto"];
  }

  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const range = maxValue - minValue;
  const padding = range > 0 ? range * 0.15 : Math.max(Math.abs(maxValue) * 0.005, 1);
  return [minValue - padding, maxValue + padding];
}

export function PnLPage({ pnl, marketStatus }) {
  const currencyCode = marketStatus?.currency_code || "USD";
  const currencyLocale = marketStatus?.currency_locale || "en-US";
  const history = pnl?.history || [];
  const current = pnl?.current;
  const baselineValue = history.length > 0 ? history[0].total_value : current?.total_value;
  const yAxisDomain = buildYAxisDomain(history, current?.total_value);

  return (
    <div className="space-y-8">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Portfolio Value" value={formatCurrency(current?.total_value, currencyCode, currencyLocale)} accent="amber" />
        <StatCard label="Cash" value={formatCurrency(current?.cash, currencyCode, currencyLocale)} accent="slate" />
        <StatCard label="Realized PnL" value={formatCurrency(current?.realized_pnl, currencyCode, currencyLocale)} accent="green" />
        <StatCard label="Unrealized PnL" value={formatCurrency(current?.unrealized_pnl, currencyCode, currencyLocale)} accent="red" />
      </section>

      <section className="rounded-[2rem] border border-slate-200 bg-white p-6 shadow-panel">
        <div className="mb-5">
          <h2 className="font-display text-2xl text-ink">Portfolio Value Over Time</h2>
          <p className="text-sm text-slate-500">Each backend PnL refresh appends a new equity snapshot.</p>
        </div>
        <div className="h-[380px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history} margin={{ top: 10, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="#e2e8f0" strokeDasharray="4 4" />
              <XAxis dataKey="timestamp" tickFormatter={formatDate} />
              <YAxis
                domain={yAxisDomain}
                tickCount={6}
                tickFormatter={(value) => formatCurrencyAxis(value, currencyCode, currencyLocale)}
              />
              {baselineValue ? (
                <ReferenceLine y={baselineValue} stroke="#94a3b8" strokeDasharray="3 3" />
              ) : null}
              <Tooltip
                formatter={(value) => formatCurrency(value, currencyCode, currencyLocale)}
                labelFormatter={(value) => new Date(value).toLocaleString()}
              />
              <Line
                type="linear"
                dataKey="total_value"
                stroke="#f97316"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 0, fill: "#ea580c" }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  );
}
