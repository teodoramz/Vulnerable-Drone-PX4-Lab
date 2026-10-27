import { useCallback, useEffect, useRef, useState } from "react";

import api from "../../api/client";
import type { PointLookup, SiteObject } from "../../components/map/site";

/** Objects to outline on the map, and what a click found. The dataset has 15,793 objects, so only those in view are fetched, and only when zoomed in. Clicks are answered by the C2 using the collision detector's own footprint test. */
export function useSiteObjects(metresPerPixel: number, threshold = 3.0) {
  const [objects, setObjects] = useState<SiteObject[]>([]);
  const [lookup, setLookup] = useState<PointLookup | null>(null);
  const [selected, setSelected] = useState<SiteObject | null>(null);
  const [loading, setLoading] = useState(false);
  // Last viewport fetched, so small pans do not refetch.
  const lastBox = useRef<string>("");

  const visible = metresPerPixel > 0 && metresPerPixel <= threshold;

  useEffect(() => {
    if (!visible) {
      setObjects([]);
      lastBox.current = "";
    }
  }, [visible]);

  const fetchForBounds = useCallback(
    async (south: number, west: number, north: number, east: number) => {
      if (!visible) return;
      const key = [south, west, north, east].map((v) => v.toFixed(4)).join(",");
      if (key === lastBox.current) return;
      lastBox.current = key;
      setLoading(true);
      try {
        const { data } = await api.get<{ objects: SiteObject[] }>("/api/site/objects", {
          params: {
            south, west, north, east,
            // Scenery is excluded: the image already draws 11,296 trees and outlines would hide everything else.
            include_scenery: false,
            sort: "height",
            limit: 1200,
          },
        });
        setObjects(data.objects ?? []);
      } catch {
        /* non-fatal: the map still works without outlines */
      } finally {
        setLoading(false);
      }
    },
    [visible],
  );

  /** Ask the C2 what is at a position. `alt` adds "would this be in my way". */
  const inspect = useCallback(async (lat: number, lon: number, alt?: number) => {
    try {
      const { data } = await api.get<PointLookup>("/api/site/objects/at", {
        params: { lat, lon, ...(alt !== undefined ? { alt } : {}) },
      });
      setLookup(data);
      setSelected(data.objects[0] ?? null);
      return data;
    } catch {
      return null;
    }
  }, []);

  const clear = useCallback(() => {
    setLookup(null);
    setSelected(null);
  }, []);

  return {
    objects,
    visible,
    loading,
    lookup,
    selected,
    setSelected,
    inspect,
    clear,
    fetchForBounds,
  };
}
