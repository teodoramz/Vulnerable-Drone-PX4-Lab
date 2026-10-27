import { useCallback, useEffect, useState } from "react";

import api from "../../api/client";

export interface PacketRow {
  ts: string;
  iface: string;
  src_ip: string;
  src_port: number | null;
  dest_ip: string;
  dest_port: number | null;
  proto: string;
  length: number;
  mavlink: {
    version: number;
    msg_id: number;
    msg: string;
    seq: number;
    sysid: number;
    compid: number;
    command?: number;
    command_name?: string;
  } | null;
  hex: string;
  ascii: string;
}

interface PacketResponse {
  sensor_reachable?: boolean;
  available?: boolean;
  captured?: number;
  capacity?: number;
  head_bytes?: number;
  packets?: PacketRow[];
  error?: string;
}

export interface BreakdownRow {
  proto: string;
  port?: number;
  packets: number;
  bytes: number;
}

interface BreakdownResponse {
  sensor_reachable?: boolean;
  total_packets?: number;
  total_bytes?: number;
  by_proto?: BreakdownRow[];
  by_port?: BreakdownRow[];
  mavlink_messages?: { msg: string; packets: number }[];
  mavlink_in_ring?: number;
  ring_size?: number;
  error?: string;
}

export interface Capture {
  name: string;
  bytes: number;
  modified: string;
}

/** Recent packets, polled from the C2's proxy of the sensor (kept off the operator socket). */
export function usePackets(intervalMs = 2000, mavlinkOnly = false, paused = false) {
  const [packets, setPackets] = useState<PacketRow[]>([]);
  const [reachable, setReachable] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get<PacketResponse>("/api/ids/packets", {
        params: { limit: 300, mavlink_only: mavlinkOnly },
      });
      setReachable(data.sensor_reachable !== false && data.available !== false);
      setError(data.error ?? null);
      setPackets(data.packets ?? []);
    } catch (e) {
      setReachable(false);
      setError(e instanceof Error ? e.message : "request failed");
    } finally {
      setLoading(false);
    }
  }, [mavlinkOnly]);

  useEffect(() => {
    if (paused) return;
    load();
    const t = window.setInterval(load, intervalMs);
    return () => window.clearInterval(t);
  }, [load, intervalMs, paused]);

  return { packets, reachable, error, loading, refresh: load };
}

export function useBreakdown(intervalMs = 3000) {
  const [data, setData] = useState<BreakdownResponse>({});
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const resp = await api.get<BreakdownResponse>("/api/ids/breakdown");
      setData(resp.data);
    } catch {
      setData({ sensor_reachable: false });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = window.setInterval(load, intervalMs);
    return () => window.clearInterval(t);
  }, [load, intervalMs]);

  return { ...data, loading, refresh: load };
}

export function useCaptures() {
  const [captures, setCaptures] = useState<Capture[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get<{ captures?: Capture[]; error?: string }>(
        "/api/ids/captures",
      );
      setCaptures(data.captures ?? []);
      setError(data.error ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "request failed");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  /** Download through the C2 with the auth header a plain <a href> cannot send. */
  const download = useCallback(async (name: string) => {
    const { data } = await api.get<Blob>(`/api/ids/captures/${encodeURIComponent(name)}`, {
      responseType: "blob",
    });
    const url = URL.createObjectURL(data);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  }, []);

  return { captures, error, refresh: load, download };
}
