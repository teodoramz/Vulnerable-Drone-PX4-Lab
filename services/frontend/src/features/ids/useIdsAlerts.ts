import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import api from "../../api/client";
import type { IdsAlert } from "../../api/types";

const MAX_ALERTS = 300;
const HIGH_PULSE_MS = 3000;

function alertKey(a: IdsAlert): string {
  return `${a.ts}|${a.sid}|${a.src_ip}|${a.src_port}|${a.dest_ip}|${a.dest_port}`;
}

export type SeverityFilter = "all" | 1 | 2 | 3;

export interface SeverityCounts {
  high: number;
  medium: number;
  low: number;
  total: number;
}

export interface UseIdsAlertsResult {
  /** Alerts after the current severity filter, newest first. */
  alerts: IdsAlert[];
  loading: boolean;
  severityFilter: SeverityFilter;
  setSeverityFilter: (s: SeverityFilter) => void;
  /** Counts across all severities (ignores the active filter). */
  counts: SeverityCounts;
  /** True for a few seconds right after a new high-severity alert lands. */
  highPulse: boolean;
  refresh: () => void;
}

/** Merges the live `ids_alert` WebSocket stream with the REST backfill (`GET /api/ids/alerts`), deduped and bounded to MAX_ALERTS. */
export function useIdsAlerts(liveAlerts: IdsAlert[]): UseIdsAlertsResult {
  const [backfill, setBackfill] = useState<IdsAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all");

  const refresh = useCallback(() => {
    setLoading(true);
    api
      .get<IdsAlert[]>("/api/ids/alerts", { params: { limit: MAX_ALERTS } })
      .then((r) => setBackfill(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const merged = useMemo<IdsAlert[]>(() => {
    const seen = new Set<string>();
    const all: IdsAlert[] = [];
    for (const a of [...liveAlerts, ...backfill]) {
      const k = alertKey(a);
      if (seen.has(k)) continue;
      seen.add(k);
      all.push(a);
    }
    all.sort((a, b) => (a.ts < b.ts ? 1 : a.ts > b.ts ? -1 : 0));
    return all.slice(0, MAX_ALERTS);
  }, [liveAlerts, backfill]);

  const counts = useMemo<SeverityCounts>(() => {
    let high = 0;
    let medium = 0;
    let low = 0;
    for (const a of merged) {
      if (a.severity === 1) high++;
      else if (a.severity === 2) medium++;
      else low++;
    }
    return { high, medium, low, total: merged.length };
  }, [merged]);

  const alerts = useMemo(
    () => (severityFilter === "all" ? merged : merged.filter((a) => a.severity === severityFilter)),
    [merged, severityFilter],
  );

  // Pulse the HIGH tile on a rising high-severity count.
  const [highPulse, setHighPulse] = useState(false);
  const prevHighRef = useRef(0);
  useEffect(() => {
    if (counts.high > prevHighRef.current) {
      setHighPulse(true);
      const t = setTimeout(() => setHighPulse(false), HIGH_PULSE_MS);
      prevHighRef.current = counts.high;
      return () => clearTimeout(t);
    }
    prevHighRef.current = counts.high;
  }, [counts.high]);

  return { alerts, loading, severityFilter, setSeverityFilter, counts, highPulse, refresh };
}
