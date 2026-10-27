import type { TelemetryDrone } from "../../api/types";

function Cell({ label, value, tone = "" }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex flex-col leading-tight">
      <span className="text-micro uppercase tracking-widest text-slate-500">{label}</span>
      <span className={`font-mono text-xs tabular-nums ${tone || "text-slate-200"}`}>{value}</span>
    </div>
  );
}

/** Live position, speed and heading. Coordinates are five decimals (~1 m). On contact loss it holds the last known fix, which feeds the Inventory position search. */
export default function TelemetryReadout({ drone }: { drone?: TelemetryDrone }) {
  const lost = !!drone?.lost;
  const flying = !!drone?.enabled && !lost;
  const speed = drone?.speed ?? 0;
  const fmt = (n: number | undefined, digits: number, suffix = "") =>
    flying && n !== undefined ? `${n.toFixed(digits)}${suffix}` : "-";

  const lat = lost ? drone?.last_known_lat : flying ? drone?.lat : undefined;
  const lon = lost ? drone?.last_known_lon : flying ? drone?.lon : undefined;
  const alt = lost ? drone?.last_known_alt : flying ? drone?.alt : undefined;
  const tone = lost ? "text-red-300" : undefined;

  return (
    <div
      className={`flex items-center gap-5 px-3 py-1.5 rounded-lg border bg-slate-900/70 ${
        lost ? "border-red-800" : "border-slate-800"
      }`}
      title={lost ? "Last known position before contact was lost" : undefined}
    >
      <Cell
        label={lost ? "Last lat" : "Lat"}
        value={lat != null ? lat.toFixed(5) : "-"}
        tone={tone}
      />
      <Cell
        label={lost ? "Last lon" : "Lon"}
        value={lon != null ? lon.toFixed(5) : "-"}
        tone={tone}
      />
      <Cell
        label={lost ? "Last alt" : "Alt"}
        value={alt != null ? `${alt.toFixed(1)} m` : "-"}
        tone={tone}
      />
      <Cell
        label="Speed"
        value={fmt(speed, 1, " m/s")}
        tone={speed > 0.3 && flying ? "text-blue-300" : "text-slate-400"}
      />
      <Cell label="Hdg" value={fmt(drone?.heading, 0, "°")} />
    </div>
  );
}
