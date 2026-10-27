import type { BreakdownRow, Capture } from "../../features/ids/useTraffic";

function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

/** Well-known ports in this lab, so a number becomes a thing. */
const PORT_NAMES: Record<number, string> = {
  22: "ssh",
  80: "http",
  443: "https",
  5432: "postgres",
  8000: "c2 api",
  8080: "ground station",
  9100: "drone lifecycle",
  9200: "sensor api",
  14540: "MAVLink (C2 offboard)",
  14550: "MAVLink (radio link)",
  8888: "micro-XRCE-DDS",
};

/** A proportion bar sized by share of the total. */
function Bar({ value, total, color }: { value: number; total: number; color: string }) {
  const pct = total > 0 ? (value / total) * 100 : 0;
  return (
    <div className="h-1.5 rounded-full bg-slate-800 overflow-hidden">
      <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}

function Table({
  title, rows, total, color, label,
}: {
  title: string;
  rows: BreakdownRow[];
  total: number;
  color: string;
  label: (r: BreakdownRow) => string;
}) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl flex flex-col min-h-0">
      <div className="shrink-0 px-3 py-1.5 border-b border-slate-800 text-label uppercase text-slate-500">
        {title}
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto p-3 flex flex-col gap-2">
        {rows.length === 0 && <div className="text-micro text-slate-600">Nothing yet.</div>}
        {rows.map((r, i) => (
          <div key={i}>
            <div className="flex items-baseline justify-between gap-3 text-micro">
              <span className="text-slate-300 truncate">{label(r)}</span>
              <span className="text-slate-500 tabular-nums shrink-0">
                {bytes(r.bytes)} · {r.packets.toLocaleString()} pkt
              </span>
            </div>
            <div className="mt-1">
              <Bar value={r.bytes} total={total} color={color} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Traffic shares by protocol and port, plus the captures on disk. */
export default function TrafficBreakdown({
  byProto,
  byPort,
  mavlinkMessages,
  totalPackets,
  totalBytes,
  captures,
  capturesError,
  onDownload,
}: {
  byProto: BreakdownRow[];
  byPort: BreakdownRow[];
  mavlinkMessages: { msg: string; packets: number }[];
  totalPackets: number;
  totalBytes: number;
  captures: Capture[];
  capturesError: string | null;
  onDownload: (name: string) => void;
}) {
  const mavTotal = mavlinkMessages.reduce((a, m) => a + m.packets, 0);

  return (
    <div className="h-full min-h-0 flex flex-col gap-3">
      <div className="shrink-0 flex gap-3 flex-wrap">
        {[
          ["Packets seen", totalPackets.toLocaleString()],
          ["Bytes seen", bytes(totalBytes)],
          ["Protocols", String(byProto.length)],
          ["Service ports", String(byPort.length)],
        ].map(([k, v]) => (
          <div key={k} className="bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 min-w-[8rem]">
            <div className="text-micro uppercase tracking-widest text-slate-600">{k}</div>
            <div className="text-sm text-slate-200 tabular-nums mt-0.5">{v}</div>
          </div>
        ))}
      </div>

      <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-3 gap-3">
        <Table
          title="By protocol"
          rows={byProto}
          total={totalBytes}
          color="#3b82f6"
          label={(r) => r.proto}
        />
        <Table
          title="By service port"
          rows={byPort}
          total={totalBytes}
          color="#10b981"
          label={(r) =>
            `${r.proto}/${r.port}${
              r.port && PORT_NAMES[r.port] ? ` - ${PORT_NAMES[r.port]}` : ""
            }`
          }
        />
        <div className="flex flex-col gap-3 min-h-0">
          <div className="bg-slate-900 border border-slate-800 rounded-xl flex flex-col min-h-0 flex-1">
            <div className="shrink-0 px-3 py-1.5 border-b border-slate-800 text-label uppercase text-slate-500">
              MAVLink message mix
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto p-3 flex flex-col gap-2">
              {mavlinkMessages.length === 0 && (
                <div className="text-micro text-slate-600">No MAVLink in the packet ring.</div>
              )}
              {mavlinkMessages.map((m) => (
                <div key={m.msg}>
                  <div className="flex items-baseline justify-between gap-3 text-micro">
                    <span className="text-cyan-300 truncate">{m.msg}</span>
                    <span className="text-slate-500 tabular-nums">{m.packets}</span>
                  </div>
                  <div className="mt-1">
                    <Bar value={m.packets} total={mavTotal} color="#22d3ee" />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl flex flex-col min-h-0 flex-1">
            <div className="shrink-0 px-3 py-1.5 border-b border-slate-800 text-label uppercase text-slate-500">
              Packet captures
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto p-3 flex flex-col gap-1">
              {capturesError && (
                <div className="text-micro text-amber-400">{capturesError}</div>
              )}
              {captures.length === 0 && !capturesError && (
                <div className="text-micro text-slate-600">
                  No captures on disk yet. Suricata rotates them as traffic accumulates.
                </div>
              )}
              {captures.map((c) => (
                <button
                  key={c.name}
                  onClick={() => onDownload(c.name)}
                  className="flex items-center justify-between gap-3 text-micro px-2 py-1 rounded border border-slate-800 text-left hover:border-slate-600 hover:bg-slate-850"
                  title="Download for Wireshark"
                >
                  <span className="text-slate-300 font-mono truncate">{c.name}</span>
                  <span className="text-slate-500 tabular-nums shrink-0">{bytes(c.bytes)}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
