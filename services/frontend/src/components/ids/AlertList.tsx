import { useMemo, useState } from "react";

import type { IdsAlert } from "../../api/types";
import Badge from "../ui/Badge";
import Toggle from "../ui/Toggle";
import { stampGmt3 } from "../../lib/time";
import { severityBorder, severityLabel, severityTone } from "./severity";

type SortMode = "newest" | "severity";

function alertId(a: IdsAlert): string {
  return `${a.ts}|${a.sid}|${a.src_ip}|${a.src_port}|${a.dest_ip}|${a.dest_port}`;
}

export default function AlertList({
  alerts,
  selectedId,
  onSelect,
}: {
  alerts: IdsAlert[];
  selectedId: string | null;
  onSelect: (a: IdsAlert) => void;
}) {
  const [sort, setSort] = useState<SortMode>("newest");

  const sorted = useMemo(() => {
    if (sort === "newest") return alerts;
    return [...alerts].sort((a, b) => a.severity - b.severity || (a.ts < b.ts ? 1 : -1));
  }, [alerts, sort]);

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="shrink-0 flex items-center justify-between px-3 py-2 border-b border-slate-800">
        <span className="text-label uppercase text-slate-500">Live Alert Stream</span>
        <Toggle
          value={sort}
          onChange={setSort}
          options={[
            { value: "newest", label: "Newest" },
            { value: "severity", label: "Severity" },
          ]}
        />
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto">
        {sorted.length === 0 && <div className="p-4 text-label text-slate-600">No alerts observed yet.</div>}
        {sorted.map((a) => {
          const id = alertId(a);
          const active = id === selectedId;
          return (
            <button
              key={id}
              onClick={() => onSelect(a)}
              className={`w-full text-left px-3 py-2 border-b border-slate-800 border-l-4 ${severityBorder(a.severity)} transition-colors ${
                active ? "bg-slate-800" : "hover:bg-slate-850"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold text-slate-200 truncate">{a.signature}</span>
                <Badge tone={severityTone(a.severity)}>{severityLabel(a.severity)}</Badge>
              </div>
              <div className="text-micro text-slate-500 font-mono mt-0.5 truncate">
                {stampGmt3(a.ts)} · {a.src_ip}:{a.src_port} → {a.dest_ip}:{a.dest_port} · {a.proto}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
