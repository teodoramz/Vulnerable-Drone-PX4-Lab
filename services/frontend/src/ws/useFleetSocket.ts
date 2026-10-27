import { useCallback, useEffect, useRef, useState } from "react";

import type { IdsAlert, LogEntry, TelemetryDrone, WsFrame } from "../api/types";

const MAX_IDS_ALERTS = 300;

export interface FleetSocket {
  drones: Record<number, TelemetryDrone>;
  logs: LogEntry[];
  connected: boolean;
  lastError: { msg: string; at: number } | null;
  idsAlerts: IdsAlert[];
  send: (msg: object) => void;
}

export function useFleetSocket(token: string | null): FleetSocket {
  const [drones, setDrones] = useState<Record<number, TelemetryDrone>>({});
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [lastError, setLastError] = useState<{ msg: string; at: number } | null>(null);
  const [idsAlerts, setIdsAlerts] = useState<IdsAlert[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!token) return;
    let closed = false;
    let retry: ReturnType<typeof setTimeout>;

    function connect() {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(token!)}`);
      wsRef.current = ws;
      ws.onopen = () => setConnected(true);
      ws.onmessage = (ev) => {
        const frame: WsFrame = JSON.parse(ev.data);
        if (frame.type === "telemetry") {
          const map: Record<number, TelemetryDrone> = {};
          for (const [id, d] of Object.entries(frame.drones)) map[Number(id)] = d;
          setDrones(map);
        } else if (frame.type === "log") {
          setLogs((prev) => [...prev.slice(-150), frame]);
        } else if (frame.type === "error") {
          setLastError({ msg: frame.msg, at: Date.now() });
        } else if (frame.type === "ids_alert") {
          setIdsAlerts((prev) => [frame.alert, ...prev].slice(0, MAX_IDS_ALERTS));
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, 2000);
      };
    }

    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      wsRef.current?.close();
    };
  }, [token]);

  const send = useCallback((msg: object) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
  }, []);

  return { drones, logs, connected, lastError, idsAlerts, send };
}
