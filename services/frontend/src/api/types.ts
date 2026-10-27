export type Role = "admin" | "operator" | "observer";

export interface User {
  id: number;
  username: string;
  role: Role;
  is_active: boolean;
}

export interface ClaimInfo {
  held: boolean;
  user_id: number | null;
  username: string | null;
  mine: boolean;
}

export interface DroneState {
  /** Contact lost: only a maintenance reset puts a replacement on a pad. The cause is deliberately not served. */
  lost?: boolean;
  last_known_lat?: number | null;
  last_known_lon?: number | null;
  last_known_alt?: number | null;
  last_contact?: string | null;
  ground_speed?: number;
  id: number;
  callsign: string;
  model: string;
  enabled: boolean;
  state: string;
  lat: number;
  lon: number;
  alt: number;
  heading: number;
  armed: boolean;
  home_lat: number;
  home_lon: number;
  claim: ClaimInfo;
}

export interface AuditEntry {
  id: number;
  ts: string;
  user_id: number | null;
  username: string;
  drone_id: number | null;
  action: string;
  params: Record<string, unknown>;
  result: string;
}

// ── live WebSocket frames ────────────────────────────────
export interface TelemetryDrone {
  /** Ground speed in m/s. */
  speed?: number;
  lost?: boolean;
  last_known_lat?: number | null;
  last_known_lon?: number | null;
  last_known_alt?: number | null;
  last_contact?: string | null;
  /** The mission the aircraft is flying, as the C2 knows it; served to every connected user. */
  target?: { lat: number; lon: number; alt: number } | null;
  patrol?: { points: [number, number][]; index: number } | null;
  enabled: boolean;
  state: string;
  lat: number;
  lon: number;
  alt: number;
  heading: number;
  armed: boolean;
  claim: { held: boolean; user_id: number | null; username: string | null };
}

export interface TelemetryFrame {
  type: "telemetry";
  drones: Record<string, TelemetryDrone>;
}
// Console log levels. `attack` is distinct from `error`: a forged command is not a platform fault.
export type LogLevel = "info" | "cmd" | "warn" | "error" | "attack";

export interface LogEntry {
  type: "log";
  level: LogLevel;
  ts: string;
  msg: string;
  drone_id: number | null;
  /** The actionable part of a failure (unreachable URL, exception type), kept apart from the headline. */
  detail?: string;
}
export type LogFrame = LogEntry;
export interface ErrorFrame {
  type: "error";
  drone_id?: number;
  msg: string;
}

// ── IDS (Suricata) alerts ────────────────────────────────
// severity: 1 = high, 2 = medium, 3 = low
export interface IdsAlert {
  ts: string;
  signature: string;
  sid: number;
  severity: number;
  category: string;
  src_ip: string;
  src_port: number;
  dest_ip: string;
  dest_port: number;
  proto: string;
  iface: string;
  /** The packet bytes that tripped the rule: base64 as Suricata emits it, plus a printable rendering. Empty when payload logging is off. */
  payload?: string;
  payload_printable?: string;
}

// ── Traffic (Suricata flow records) ──────────────────────
export interface Flow {
  ts: string;
  src_ip: string;
  src_port: number | null;
  dest_ip: string;
  dest_port: number | null;
  proto: string;
  iface: string;
  state: string;
  pkts_toserver: number;
  pkts_toclient: number;
  bytes_toserver: number;
  bytes_toclient: number;
  start: string;
  end: string;
}

/** A live flow from the sensor's rolling counters, as opposed to `Flow`, which Suricata logs only once the connection ends. */
export interface LiveFlow {
  src_ip: string;
  src_port: number | null;
  dest_ip: string;
  dest_port: number | null;
  proto: string;
  iface: string;
  packets: number;
  bytes: number;
  age_s: number;
  idle_s: number;
  pps: number;
}

export interface IdsAlertFrame {
  type: "ids_alert";
  alert: IdsAlert;
}

export type WsFrame = TelemetryFrame | LogFrame | ErrorFrame | IdsAlertFrame;

// ── public drone status (GET /api/public/drone, no auth) ──
export interface PublicDroneStatus {
  drone_id: number;
  callsign: string;
  state: "alive" | "missing";
  since?: string | null;
  flying?: boolean;
  last_known?: { lat: number | null; lon: number | null; alt_m: number | null };
  last_contact?: string | null;
}
