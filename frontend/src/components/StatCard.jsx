export function StatCard({ label, value, accent = "amber" }) {
  const accents = {
    amber: "from-amber-100 to-yellow-50 border-amber-200",
    green: "from-green-100 to-emerald-50 border-green-200",
    red: "from-red-100 to-rose-50 border-red-200",
    slate: "from-slate-100 to-slate-50 border-slate-200"
  };

  return (
    <div className={`rounded-3xl border bg-gradient-to-br p-5 shadow-panel ${accents[accent]}`}>
      <p className="text-sm uppercase tracking-[0.2em] text-slate-500">{label}</p>
      <p className="mt-3 font-display text-3xl text-ink">{value}</p>
    </div>
  );
}
