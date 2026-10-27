import { useCallback, useEffect, useState } from "react";

import api from "../../api/client";
import type { LiveFlow } from "../../api/types";

interface LiveResponse {
  available: boolean;
  window_s?: number;
  ifaces?: string[];
  total_packets?: number;
  total_bytes?: number;
  flows: LiveFlow[];
  error?: string;
  sensor_url?: string;
}

/** Live traffic, polled from the C2's proxy of the sensor's live tap (kept off the operator socket). */
export function useFlows(intervalMs = 2000) {
  const [flows, setFlows] = useState<LiveFlow[]>([]);
  const [totals, setTotals] = useState<{ packets: number; bytes: number }>({ packets: 0, bytes: 0 });
  const [reachable, setReachable] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get<LiveResponse>("/api/ids/live", { params: { limit: 200 } });
      setFlows(data.flows ?? []);
      setTotals({ packets: data.total_packets ?? 0, bytes: data.total_bytes ?? 0 });
      setReachable(data.available);
      setError(data.available ? null : data.error ?? "live capture unavailable");
    } catch (e: any) {
      setReachable(false);
      setError(e?.message ?? "request failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, intervalMs);
    return () => clearInterval(t);
  }, [load, intervalMs]);

  return { flows, totals, reachable, error, loading, refresh: load };
}
