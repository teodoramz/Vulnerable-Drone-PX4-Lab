import { objectLabel, prettyType, type PointLookup, type SiteObject } from "../map/site";

/** Fixed-order fields first; any other dataset fields are listed after. */
const LEAD = ["lat", "lon", "height_m", "length_m", "width_m", "grid_ref"] as const;

const HIDDEN = new Set([
  "id",
  "type",
  "px",
  "footprint_latlon",
  "path_latlon",
  "thresholds",
  "color_hex",
  "tail_color",
  ...LEAD,
]);

function fmt(key: string, value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "number") {
    return key.endsWith("_m") || key.endsWith("_m2") || key.endsWith("_deg")
      ? value.toFixed(value < 10 ? 1 : 0)
      : String(value);
  }
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3 py-0.5 border-b border-slate-800/60 last:border-0">
      <span className="text-slate-500 shrink-0">{k.replace(/_/g, " ")}</span>
      <span className="text-slate-200 tabular-nums text-right break-all">{v}</span>
    </div>
  );
}

/** What is at a point on the map, using the C2's own footprint test so it agrees with collision detection. */
export default function ObjectInspector({
  lookup,
  selected,
  onSelect,
  onClose,
  onGoHere,
}: {
  lookup: PointLookup | null;
  selected: SiteObject | null;
  onSelect: (o: SiteObject) => void;
  onClose: () => void;
  onGoHere?: (lat: number, lon: number) => void;
}) {
  if (!lookup) {
    return (
      <div className="p-3 text-micro text-slate-500 leading-relaxed">
        Click the map to inspect a position: what is there, how tall it is, and whether it
        is inside the operational area.
        <div className="mt-2 text-slate-600">
          Zoom in past ~3 m/px and the structures are outlined and clickable.
        </div>
      </div>
    );
  }

  const o = selected;
  const extras = o
    ? Object.entries(o).filter(([k, v]) => !HIDDEN.has(k) && v !== null && v !== undefined)
    : [];

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-start justify-between gap-2 px-3 py-2 border-b border-slate-800">
        <div className="min-w-0">
          <div className="text-label uppercase text-slate-500">Position</div>
          <div className="text-xs text-slate-300 tabular-nums">
            {lookup.lat.toFixed(5)}, {lookup.lon.toFixed(5)}
            {lookup.grid_ref && <span className="text-slate-500"> · {lookup.grid_ref}</span>}
          </div>
          {lookup.inside_operational_area ? (
            <div className="text-micro text-emerald-500 mt-0.5">inside the operational area</div>
          ) : (
            <div className="text-micro text-amber-400 mt-0.5">
              outside the operational area
              {lookup.metres_outside_area != null &&
                ` - ${lookup.metres_outside_area.toFixed(0)} m beyond`}
            </div>
          )}
        </div>
        <div className="flex flex-col gap-1 shrink-0">
          {onGoHere && (
            <button
              onClick={() => onGoHere(lookup.lat, lookup.lon)}
              className="text-micro px-1.5 py-0.5 rounded border border-slate-700 text-slate-400 hover:text-slate-200 hover:border-slate-500"
              title="Copy this position into the go-to coordinates"
            >
              use as target
            </button>
          )}
          <button
            onClick={onClose}
            className="text-micro px-1.5 py-0.5 rounded border border-slate-700 text-slate-500 hover:text-slate-300"
          >
            close
          </button>
        </div>
      </div>

      {lookup.objects.length === 0 ? (
        <div className="p-3 text-micro text-slate-500">
          Nothing here - open ground.
          {!lookup.inside_operational_area && (
            <div className="mt-1 text-slate-600">
              An aircraft lost at a position like this one was flown out of the area, not
              into anything.
            </div>
          )}
        </div>
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto">
          {/* Several objects can cover a point; tallest first, matching collision detection order. */}
          {lookup.objects.length > 1 && (
            <div className="flex flex-wrap gap-1 px-3 pt-2">
              {lookup.objects.map((c) => (
                <button
                  key={c.id}
                  onClick={() => onSelect(c)}
                  className={`text-micro px-1.5 py-0.5 rounded border ${
                    c.id === o?.id
                      ? "border-blue-500 text-blue-300 bg-blue-500/10"
                      : "border-slate-700 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {prettyType(c.type)}
                </button>
              ))}
            </div>
          )}

          {o && (
            <div className="px-3 py-2">
              <div className="text-sm font-semibold text-slate-100">{objectLabel(o)}</div>
              <div className="text-micro text-slate-500 font-mono">{o.id}</div>

              <div className="mt-2 text-micro">
                <Row k="latitude" v={o.lat.toFixed(6)} />
                <Row k="longitude" v={o.lon.toFixed(6)} />
                <Row k="height" v={`${o.height_m.toFixed(1)} m`} />
                <Row
                  k="footprint"
                  v={`${o.length_m.toFixed(1)} × ${o.width_m.toFixed(1)} m`}
                />
                {o.grid_ref && <Row k="grid" v={o.grid_ref} />}
                {extras.map(([k, v]) => (
                  <Row key={k} k={k} v={fmt(k, v)} />
                ))}
              </div>

              {o.height_m >= 0.5 && (
                <div className="mt-2 rounded border border-amber-800/60 bg-amber-500/5 px-2 py-1 text-micro text-amber-300">
                  Obstruction to {o.height_m.toFixed(1)} m - fly above it to clear it.
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {lookup.would_hit !== undefined && (
        <div className="px-3 py-1.5 border-t border-slate-800 text-micro">
          {lookup.would_hit ? (
            <span className="text-red-400">
              At {lookup.alt?.toFixed(0)} m this position is blocked by{" "}
              {objectLabel(lookup.would_hit).toLowerCase()}.
            </span>
          ) : (
            <span className="text-emerald-500">
              Clear at {lookup.alt?.toFixed(0)} m.
            </span>
          )}
        </div>
      )}
    </div>
  );
}
