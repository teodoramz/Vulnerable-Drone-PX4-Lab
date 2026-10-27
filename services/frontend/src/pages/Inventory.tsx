import { useCallback, useEffect, useMemo, useState } from "react";

import api from "../api/client";
import {
  objectLabel,
  prettyType,
  type ObjectPage,
  type SiteDef,
  type SiteObject,
} from "../components/map/site";
import { inputClass } from "../components/ui/Field";

const PAGE = 50;

/** The site inventory: every object on the map, searchable. Used to explain signal loss from a last known position. Filtering happens on the C2 (15,793 objects, 3.9 MB). */
export default function Inventory() {
  const [site, setSite] = useState<SiteDef | null>(null);
  const [page, setPage] = useState<ObjectPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<SiteObject | null>(null);

  // filters
  const [q, setQ] = useState("");
  const [types, setTypes] = useState<Set<string>>(new Set());
  const [minHeight, setMinHeight] = useState("");
  const [insideOnly, setInsideOnly] = useState<"" | "true" | "false">("");
  // Coordinate search, held as text so partial input and pasted "lat, lon" from the audit log work.
  const [nearLat, setNearLat] = useState("");
  const [nearLon, setNearLon] = useState("");
  const [radius, setRadius] = useState("150");
  const [includeScenery, setIncludeScenery] = useState(false);
  const [sort, setSort] = useState("type");
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    api
      .get<SiteDef>("/api/site")
      .then((r) => setSite(r.data))
      .catch(() => setError("Could not load the site."));
  }, []);

  const query = useMemo(() => {
    const p = new URLSearchParams();
    if (q.trim()) p.set("q", q.trim());
    types.forEach((t) => p.append("type", t));
    if (minHeight.trim()) p.set("min_height", minHeight.trim());
    if (insideOnly) p.set("inside_area", insideOnly);
    const la = Number(nearLat);
    const lo = Number(nearLon);
    if (nearLat.trim() && nearLon.trim() && Number.isFinite(la) && Number.isFinite(lo)) {
      p.set("near_lat", String(la));
      p.set("near_lon", String(lo));
      p.set("radius_m", String(Number(radius) || 0));
    }
    p.set("include_scenery", String(includeScenery));
    p.set("sort", sort);
    p.set("offset", String(offset));
    p.set("limit", String(PAGE));
    return p.toString();
  }, [q, types, minHeight, insideOnly, includeScenery, sort, offset, nearLat, nearLon, radius]);

  useEffect(() => {
    let live = true;
    setLoading(true);
    // Debounced: no request per keystroke.
    const t = window.setTimeout(() => {
      api
        .get<ObjectPage>(`/api/site/objects?${query}`)
        .then((r) => {
          if (live) {
            setPage(r.data);
            setError(null);
          }
        })
        .catch(() => live && setError("Search failed."))
        .finally(() => live && setLoading(false));
    }, 220);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
  }, [query]);

  // Any filter change returns to the first page.
  const resetPaging = useCallback(() => setOffset(0), []);

  const toggleType = useCallback(
    (t: string) => {
      setTypes((prev) => {
        const next = new Set(prev);
        next.has(t) ? next.delete(t) : next.add(t);
        return next;
      });
      resetPaging();
    },
    [resetPaging],
  );

  const clearFilters = useCallback(() => {
    setQ("");
    setTypes(new Set());
    setMinHeight("");
    setInsideOnly("");
    setIncludeScenery(false);
    setSort("type");
    setOffset(0);
    setNearLat("");
    setNearLon("");
    setRadius("150");
  }, []);

  const total = page?.total ?? 0;
  const shown = page?.objects ?? [];
  const searchingNear = !!nearLat.trim() && !!nearLon.trim();
  const activeFilters =
    !!q.trim() || types.size > 0 || !!minHeight.trim() || !!insideOnly || includeScenery ||
    searchingNear;

  /** Split a pasted "lat, lon" (or "lat lon") across both boxes. */
  const takePair = useCallback((text: string, which: "lat" | "lon") => {
    const parts = text.split(/[,;\s]+/).filter(Boolean);
    if (parts.length >= 2 && Number.isFinite(Number(parts[0])) && Number.isFinite(Number(parts[1]))) {
      setNearLat(parts[0]);
      setNearLon(parts[1]);
    } else if (which === "lat") {
      setNearLat(text);
    } else {
      setNearLon(text);
    }
    resetPaging();
  }, [resetPaging]);

  return (
    <div className="h-full flex flex-col gap-3 p-3 min-h-0">
      <div className="shrink-0">
        <h1 className="text-sm font-semibold text-slate-200">Site inventory</h1>
        <p className="text-micro text-slate-500 mt-0.5">
          {site
            ? `${site.total_objects.toLocaleString()} objects across ${site.map_width_m / 1000} × ${
                site.map_height_m / 1000
              } km. Every one has a position, a footprint and a height.`
            : "Loading…"}
        </p>
      </div>

      {/* ── filters ── */}
      <div className="shrink-0 bg-slate-900 border border-slate-800 rounded-xl p-3 flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              resetPaging();
            }}
            placeholder="Search id, type, use, species, model, stand…"
            className={`${inputClass} flex-1 min-w-[16rem] px-2 py-1 text-xs`}
            aria-label="Search objects"
          />
          <input
            value={minHeight}
            onChange={(e) => {
              setMinHeight(e.target.value);
              resetPaging();
            }}
            placeholder="min height m"
            inputMode="decimal"
            className={`${inputClass} w-28 px-2 py-1 text-xs tabular-nums`}
            aria-label="Minimum height in metres"
          />
          <select
            value={insideOnly}
            onChange={(e) => {
              setInsideOnly(e.target.value as "" | "true" | "false");
              resetPaging();
            }}
            className={`${inputClass} px-2 py-1 text-xs`}
            aria-label="Operational area"
          >
            <option value="">Anywhere</option>
            <option value="true">Inside the area</option>
            <option value="false">Outside the area</option>
          </select>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className={`${inputClass} px-2 py-1 text-xs`}
            aria-label="Sort by"
          >
            {searchingNear && <option value="distance">Sort: nearest</option>}
            <option value="type">Sort: type</option>
            <option value="height">Sort: tallest</option>
            <option value="size">Sort: largest</option>
            <option value="id">Sort: id</option>
          </select>
          <label className="flex items-center gap-1.5 text-micro text-slate-400 cursor-pointer">
            <input
              type="checkbox"
              checked={includeScenery}
              onChange={(e) => {
                setIncludeScenery(e.target.checked);
                resetPaging();
              }}
            />
            include scenery
          </label>
          {activeFilters && (
            <button
              onClick={clearFilters}
              className="text-micro px-2 py-1 rounded border border-slate-700 text-slate-400 hover:text-slate-200"
            >
              clear
            </button>
          )}
        </div>

        {/* Coordinate search: paste a last known position from the Audit tab. */}
        <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-slate-800">
          <span className="text-micro uppercase tracking-widest text-slate-600 shrink-0">
            Near position
          </span>
          <input
            value={nearLat}
            onChange={(e) => takePair(e.target.value, "lat")}
            placeholder="latitude"
            inputMode="decimal"
            className={`${inputClass} w-36 px-2 py-1 text-xs tabular-nums`}
            aria-label="Search near latitude"
          />
          <input
            value={nearLon}
            onChange={(e) => takePair(e.target.value, "lon")}
            placeholder="longitude"
            inputMode="decimal"
            className={`${inputClass} w-36 px-2 py-1 text-xs tabular-nums`}
            aria-label="Search near longitude"
          />
          <span className="text-micro text-slate-600">within</span>
          <input
            value={radius}
            onChange={(e) => {
              setRadius(e.target.value);
              resetPaging();
            }}
            inputMode="decimal"
            className={`${inputClass} w-20 px-2 py-1 text-xs tabular-nums`}
            aria-label="Search radius in metres"
          />
          <span className="text-micro text-slate-600">m</span>
          {searchingNear ? (
            <span className="text-micro text-blue-300">
              nearest first · distance to each footprint
            </span>
          ) : (
            <span className="text-micro text-slate-600">
              paste “lat, lon” into either box
            </span>
          )}
        </div>

        {/* Type chips with counts. Scenery types (11,296 trees) are dimmed and hidden by default. */}
        {site && (
          <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
            {site.object_types
              .filter((t) => includeScenery || !t.scenery)
              .map((t) => (
                <button
                  key={t.type}
                  onClick={() => toggleType(t.type)}
                  title={`${t.count} · up to ${t.max_height_m.toFixed(1)} m`}
                  className={`text-micro px-1.5 py-0.5 rounded border transition-colors ${
                    types.has(t.type)
                      ? "border-blue-500 text-blue-300 bg-blue-500/10"
                      : t.scenery
                        ? "border-slate-800 text-slate-600 hover:text-slate-400"
                        : "border-slate-700 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {prettyType(t.type)}
                  <span className="ml-1 opacity-60 tabular-nums">{t.count}</span>
                </button>
              ))}
          </div>
        )}
      </div>

      {/* ── results ── */}
      <div className="flex-1 min-h-0 flex gap-3">
        <div className="flex-1 min-w-0 bg-slate-900 border border-slate-800 rounded-xl flex flex-col min-h-0">
          <div className="shrink-0 px-3 py-1.5 border-b border-slate-800 flex items-center justify-between text-micro">
            <span className="text-slate-400 tabular-nums">
              {error ? (
                <span className="text-red-400">{error}</span>
              ) : loading ? (
                "searching…"
              ) : (
                <>
                  {total.toLocaleString()} match{total === 1 ? "" : "es"}
                  {total > PAGE && (
                    <span className="text-slate-600">
                      {" "}
                      · showing {offset + 1}-{Math.min(offset + PAGE, total)}
                    </span>
                  )}
                </>
              )}
            </span>
            {total > PAGE && (
              <span className="flex gap-1">
                <button
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE))}
                  className="px-1.5 py-0.5 rounded border border-slate-700 text-slate-400 disabled:opacity-30 hover:text-slate-200"
                >
                  prev
                </button>
                <button
                  disabled={offset + PAGE >= total}
                  onClick={() => setOffset(offset + PAGE)}
                  className="px-1.5 py-0.5 rounded border border-slate-700 text-slate-400 disabled:opacity-30 hover:text-slate-200"
                >
                  next
                </button>
              </span>
            )}
          </div>

          <div className="flex-1 min-h-0 overflow-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-slate-900 text-micro uppercase text-slate-600">
                <tr className="border-b border-slate-800">
                  <th className="text-left font-medium px-3 py-1.5">Object</th>
                  <th className="text-right font-medium px-2 py-1.5">Height</th>
                  <th className="text-right font-medium px-2 py-1.5">Size (m)</th>
                  <th className="text-right font-medium px-2 py-1.5">Latitude</th>
                  <th className="text-right font-medium px-2 py-1.5">Longitude</th>
                  <th className="text-center font-medium px-2 py-1.5">Grid</th>
                  {searchingNear && (
                    <th className="text-right font-medium px-2 py-1.5">Distance</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {shown.map((o) => (
                  <tr
                    key={o.id}
                    onClick={() => setSelected(o)}
                    className={`border-b border-slate-800/60 cursor-pointer ${
                      selected?.id === o.id ? "bg-slate-800" : "hover:bg-slate-850"
                    }`}
                  >
                    <td className="px-3 py-1">
                      <div className="text-slate-200">{objectLabel(o)}</div>
                      <div className="text-micro text-slate-600 font-mono">{o.id}</div>
                    </td>
                    <td className="px-2 py-1 text-right tabular-nums text-slate-300">
                      {o.height_m.toFixed(1)}
                    </td>
                    <td className="px-2 py-1 text-right tabular-nums text-slate-400">
                      {o.length_m.toFixed(0)} × {o.width_m.toFixed(0)}
                    </td>
                    <td className="px-2 py-1 text-right tabular-nums text-slate-400">
                      {o.lat.toFixed(5)}
                    </td>
                    <td className="px-2 py-1 text-right tabular-nums text-slate-400">
                      {o.lon.toFixed(5)}
                    </td>
                    <td className="px-2 py-1 text-center text-slate-500">{o.grid_ref ?? "-"}</td>
                    {searchingNear && (
                      <td className="px-2 py-1 text-right tabular-nums">
                        {typeof o.distance_m === "number" ? (
                          o.distance_m === 0 ? (
                            <span className="text-amber-300">at this point</span>
                          ) : (
                            <span className="text-slate-300">{o.distance_m.toFixed(1)} m</span>
                          )
                        ) : (
                          "-"
                        )}
                      </td>
                    )}
                  </tr>
                ))}
                {!loading && shown.length === 0 && (
                  <tr>
                    <td colSpan={searchingNear ? 7 : 6} className="px-3 py-6 text-center text-slate-600">
                      Nothing matches.
                      {!includeScenery && (
                        <div className="mt-1 text-micro">
                          Trees, fields and solar tables are hidden - tick “include scenery”.
                        </div>
                      )}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* ── detail ── */}
        <div className="w-80 shrink-0 bg-slate-900 border border-slate-800 rounded-xl overflow-y-auto">
          {selected ? (
            <div className="p-3">
              <div className="text-sm font-semibold text-slate-100">{objectLabel(selected)}</div>
              <div className="text-micro text-slate-600 font-mono mb-2">{selected.id}</div>
              <div className="text-micro">
                {Object.entries(selected)
                  .filter(
                    ([k, v]) =>
                      v !== null &&
                      v !== undefined &&
                      !["id", "footprint_latlon", "path_latlon", "px"].includes(k),
                  )
                  .map(([k, v]) => (
                    <div
                      key={k}
                      className="flex justify-between gap-3 py-0.5 border-b border-slate-800/60 last:border-0"
                    >
                      <span className="text-slate-500">{k.replace(/_/g, " ")}</span>
                      <span className="text-slate-200 tabular-nums text-right break-all">
                        {typeof v === "boolean"
                          ? v
                            ? "yes"
                            : "no"
                          : typeof v === "object"
                            ? JSON.stringify(v)
                            : String(v)}
                      </span>
                    </div>
                  ))}
              </div>
              {selected.height_m >= 0.5 && (
                <div className="mt-2 rounded border border-amber-800/60 bg-amber-500/5 px-2 py-1 text-micro text-amber-300">
                  Obstruction to {selected.height_m.toFixed(1)} m. An aircraft below that
                  height at this position would not survive the encounter.
                </div>
              )}
            </div>
          ) : (
            <div className="p-3 text-micro text-slate-500 leading-relaxed">
              Select an object for its full record.
              <div className="mt-2 text-slate-600">
                Looking into a lost aircraft? Take the last known position from the{" "}
                <span className="text-slate-400">Audit</span> tab and search the grid square
                here, or sort by height to see what was tall enough to matter.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
