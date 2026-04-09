const classes = {
  BUY: "bg-green-100 text-green-800",
  SELL: "bg-red-100 text-red-800",
  HOLD: "bg-slate-100 text-slate-700",
  AVOID: "bg-amber-100 text-amber-900"
};

export function SignalBadge({ value }) {
  return (
    <span className={`rounded-full px-3 py-1 text-xs font-semibold ${classes[value] || classes.HOLD}`}>
      {value}
    </span>
  );
}
