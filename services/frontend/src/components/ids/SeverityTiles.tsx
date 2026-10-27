import type { SeverityCounts, SeverityFilter } from "../../features/ids/useIdsAlerts";

const TILES: { key: SeverityFilter; label: string; countKey: keyof SeverityCounts; tone: string; ring: string }[] = [
  { key: 1, label: "High", countKey: "high", tone: "text-red-300 bg-red-600/10 border-red-800", ring: "ring-red-500" },
  { key: 2, label: "Medium", countKey: "medium", tone: "text-amber-300 bg-amber-600/10 border-amber-800", ring: "ring-amber-500" },
  { key: 3, label: "Low", countKey: "low", tone: "text-blue-300 bg-blue-600/10 border-blue-800", ring: "ring-blue-500" },
];

/** Severity counters that double as the filter; the HIGH tile pulses on a new high-severity alert. */
export default function SeverityTiles({
  counts,
  severityFilter,
  onFilter,
  highPulse,
}: {
  counts: SeverityCounts;
  severityFilter: SeverityFilter;
  onFilter: (s: SeverityFilter) => void;
  highPulse: boolean;
}) {
  return (
    <div className="flex items-stretch gap-2">
      <button
        onClick={() => onFilter("all")}
        className={`flex flex-col justify-center px-3 py-1.5 rounded-lg border text-left transition-colors ${
          severityFilter === "all" ? "bg-slate-700 border-slate-600 text-slate-100" : "bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200"
        }`}
      >
        <span className="text-lg font-bold tabular-nums leading-none">{counts.total}</span>
        <span className="text-micro uppercase tracking-wider mt-0.5">All</span>
      </button>

      {TILES.map((t) => {
        const active = severityFilter === t.key;
        const isHighPulsing = t.key === 1 && highPulse;
        return (
          <button
            key={t.key}
            onClick={() => onFilter(t.key)}
            className={`flex flex-col justify-center px-3 py-1.5 rounded-lg border text-left transition-all ${t.tone} ${
              active ? `ring-2 ${t.ring}` : ""
            } ${isHighPulsing ? "animate-alert-flash" : ""}`}
          >
            <span className="text-lg font-bold tabular-nums leading-none">{counts[t.countKey]}</span>
            <span className="text-micro uppercase tracking-wider mt-0.5">{t.label}</span>
          </button>
        );
      })}
    </div>
  );
}
