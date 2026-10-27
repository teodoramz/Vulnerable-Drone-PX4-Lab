import { useCallback, useEffect, useRef, useState } from "react";

import type { DroneState } from "../../api/types";
import type { LatLon } from "../../components/map/MapView";
import { metresBetween, routeLatLon, type SiteDef } from "../../components/map/site";
import type { Selection } from "./useFleetCommands";

const PERIMETER_KEY = "patrol.route";
const ROUTE_KEY = "patrol.routeKey";

function loadStored<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}
function saveStored(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable - non-fatal */
  }
}

function lonOffset(lat: number, meters: number): number {
  return meters / (111320.0 * Math.cos((lat * Math.PI) / 180));
}
function swarmOffsetMeters(id: number): number {
  if (id <= 0) return 0;
  const step = Math.ceil(id / 2) * 3;
  return id % 2 === 1 ? step : -step;
}

export type ClickMode = "target" | "perimeter" | "delete";

interface Params {
  registry: DroneState[];
  controlTargets: number[];
  selected: Selection;
  site: SiteDef | null;
}

export interface MissionPlanner {
  clickMode: ClickMode;
  setClickMode: (m: ClickMode) => void;

  perimeter: LatLon[];
  targets: Record<number, LatLon>;

  /** Key of the loaded predefined route, or "" when drawn by hand. */
  routeKey: string;
  selectRoute: (key: string) => void;

  /** Go-to destination as typed text, so a half-entered number survives keystrokes. Clicking the map fills it. */
  targetLat: string;
  targetLon: string;
  setTargetLat: (v: string) => void;
  setTargetLon: (v: string) => void;

  onMapClick: (lat: number, lon: number) => void;
  removePerimeterPoint: (i: number) => void;
  undoPerimeterPoint: () => void;
  removeTarget: (id: number) => void;
  clearMarks: () => void;
  clearTargets: (ids: number[]) => void;
}

/** Map interaction and mission planning: the patrol route and nav targets,
 * map click behaviour, and loading the site's predefined routes. The route
 * persists to localStorage; command dispatch stays in useFleetCommands. */
export function useMissionPlanner({ registry, controlTargets, selected, site }: Params): MissionPlanner {
  const [clickMode, setClickMode] = useState<ClickMode>("target");
  const [perimeter, setPerimeter] = useState<LatLon[]>(() => loadStored<LatLon[]>(PERIMETER_KEY, []));
  const [targets, setTargets] = useState<Record<number, LatLon>>({});
  // Loaded predefined route; empty means hand-drawn (the selector shows "Custom").
  const [routeKey, setRouteKey] = useState<string>(() => loadStored<string>(ROUTE_KEY, ""));
  const [targetLat, setTargetLat] = useState<string>("");
  const [targetLon, setTargetLon] = useState<string>("");

  // If anything was ever stored, an empty array is deliberate; do not reseed.
  const everStoredRef = useRef(loadStored<LatLon[] | null>(PERIMETER_KEY, null) !== null);

  useEffect(() => saveStored(PERIMETER_KEY, perimeter), [perimeter]);
  useEffect(() => saveStored(ROUTE_KEY, routeKey), [routeKey]);

  // Seed the predefined patrol route once the registry (home) and site definition are known.
  useEffect(() => {
    if (everStoredRef.current) return;
    if (!site) return;
    everStoredRef.current = true;
    setPerimeter(routeLatLon(site, site.default_route));
    setRouteKey(site.default_route);
  }, [registry, site]);

  /** Load one of the site's predefined routes. */
  const selectRoute = useCallback(
    (key: string) => {
      if (!site || !site.routes[key]) return;
      setPerimeter(routeLatLon(site, key));
      setRouteKey(key);
    },
    [registry, site],
  );

  // ── map click: set nav target OR append a perimeter point ──
  const setTargetAt = useCallback(
    (lat: number, lon: number) => {
      if (controlTargets.length === 0) return;
      setTargets((prev) => {
        const next = { ...prev };
        if (selected === "SWARM") {
          for (const id of controlTargets) {
            const off = swarmOffsetMeters(id);
            next[id] = { lat, lon: lon + (off ? lonOffset(lat, off) : 0) };
          }
        } else {
          next[selected as number] = { lat, lon };
        }
        return next;
      });
    },
    [controlTargets, selected],
  );

  // Text boxes keep partial input ("43.99", "-"); the marker moves once the pair parses.
  const applyTypedTarget = useCallback(
    (latText: string, lonText: string) => {
      const lat = Number(latText);
      const lon = Number(lonText);
      if (!latText.trim() || !lonText.trim()) return;
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
      if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return;
      setTargetAt(lat, lon);
    },
    [setTargetAt],
  );

  const setTargetLatText = useCallback(
    (v: string) => {
      setTargetLat(v);
      applyTypedTarget(v, targetLon);
    },
    [applyTypedTarget, targetLon],
  );
  const setTargetLonText = useCallback(
    (v: string) => {
      setTargetLon(v);
      applyTypedTarget(targetLat, v);
    },
    [applyTypedTarget, targetLat],
  );

  // A hand edit no longer matches the named route, so fall back to "Custom".
  const removePerimeterPoint = useCallback((i: number) => {
    setRouteKey("");
    setPerimeter((prev) => prev.filter((_, idx) => idx !== i));
  }, []);
  const undoPerimeterPoint = useCallback(() => {
    setRouteKey("");
    setPerimeter((prev) => prev.slice(0, -1));
  }, []);
  const removeTarget = useCallback(
    (id: number) =>
      setTargets((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      }),
    [],
  );
  const clearTargets = useCallback(
    (ids: number[]) =>
      setTargets((prev) => {
        const next = { ...prev };
        ids.forEach((id) => delete next[id]);
        return next;
      }),
    [],
  );
  const clearMarks = useCallback(() => {
    setTargets({});
    setPerimeter([]);
    setRouteKey("");
    setTargetLat("");
    setTargetLon("");
  }, []);

  // Delete mode: remove the closest perimeter point or target; perimeter points win ties.
  const deleteNearest = useCallback(
    (lat: number, lon: number) => {
      const here = { lat, lon };
      let pIdx = -1;
      let pDist = Infinity;
      perimeter.forEach((p, i) => {
        const d = metresBetween(here, p);
        if (d < pDist) [pDist, pIdx] = [d, i];
      });
      let tId = -1;
      let tDist = Infinity;
      for (const [id, t] of Object.entries(targets)) {
        const d = metresBetween(here, t);
        if (d < tDist) [tDist, tId] = [d, Number(id)];
      }
      if (pIdx >= 0 && pDist <= tDist) removePerimeterPoint(pIdx);
      else if (tId >= 0) removeTarget(tId);
    },
    [perimeter, targets, removePerimeterPoint, removeTarget],
  );

  const onMapClick = useCallback(
    (lat: number, lon: number) => {
      if (clickMode === "perimeter") {
        setRouteKey("");
        setPerimeter((prev) => [...prev, { lat, lon }]);
      } else if (clickMode === "delete") {
        deleteNearest(lat, lon);
      } else {
        setTargetAt(lat, lon);
        // Also fill the typed boxes so the operator can click roughly, then correct.
        setTargetLat(lat.toFixed(6));
        setTargetLon(lon.toFixed(6));
      }
    },
    [clickMode, deleteNearest, setTargetAt],
  );

  return {
    clickMode,
    setClickMode,
    perimeter,
    targets,
    routeKey,
    selectRoute,
    targetLat,
    targetLon,
    setTargetLat: setTargetLatText,
    setTargetLon: setTargetLonText,
    onMapClick,
    removePerimeterPoint,
    undoPerimeterPoint,
    removeTarget,
    clearMarks,
    clearTargets,
  };
}
