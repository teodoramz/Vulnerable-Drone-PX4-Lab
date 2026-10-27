import { useMemo, useState } from "react";

import type { LiveFlow } from "../../api/types";

/** Ports that identify a component, so a row reads as who talked to whom. */
const PORT_ROLE: Record<number, string> = {
  22: "ssh",
  80: "http",
  443: "https",
  5432: "db",
  8000: "c2",
  8080: "gcs",
  9100: "drone lifecycle",
  9200: "sensor",
  14540: "MAVLink telemetry",
  14550: "MAVLink radio",
};

function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function ago(seconds: number): string {
  if (seconds < 1) return "now";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.round(seconds / 60)}m`;
}

type SortKey = "idle" | "packets" | "bytes" | "rate" | "src" | "dest";

export default function FlowTable({ flows, totals }: { flows: LiveFlow[]; totals: { packets: number; bytes: number } }) {
  const [ifaceFilter, setIfaceFilter] = useState<string>("all");
  const [protoFilter, setProtoFilter] = useState<string>("all");
  const [q, setQ] = useState("");
  const [portFilter, setPortFilter] = useState("");
  const [onlyRadio, setOnlyRadio] = useState(false);
  const [onlyUnknown, setOnlyUnknown] = useState(false);
  const [sort, setSort] = useState<SortKey>("idle");

  const ifaces = useMemo(
    () => Array.from(new Set(flows.map((f) => f.iface).filter(Boolean))).sort(),
    [flows],
  );
  const protos = useMemo(
    () => Array.from(new Set(flows.map((f) => f.proto).filter(Boolean))).sort(),
    [flows],
  );

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const port = portFilter.trim();
    let rows = flows.filter((f) => {
      if (ifaceFilter !== "all" && f.iface !== ifaceFilter) return false;
      if (protoFilter !== "all" && f.proto !== protoFilter) return false;
      if (onlyRadio && f.dest_port !== 14550 && f.src_port !== 14550) return false;
      // "Unknown peers": neither end serves a port this lab expects.
      if (onlyUnknown) {
        const known =
          (f.dest_port != null && PORT_ROLE[f.dest_port]) ||
          (f.src_port != null && PORT_ROLE[f.src_port]);
        if (known) return false;
      }
      if (port && String(f.src_port) !== port && String(f.dest_port) !== port) return false;
      if (needle) {
        const hay = `${f.src_ip}:${f.src_port} ${f.dest_ip}:${f.dest_port} ${f.proto} ${f.iface}`.toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });
    const by: Record<SortKey, (a: LiveFlow, b: LiveFlow) => number> = {
      idle: (a, b) => a.idle_s - b.idle_s,
      packets: (a, b) => b.packets - a.packets,
      bytes: (a, b) => b.bytes - a.bytes,
      rate: (a, b) => b.pps - a.pps,
      src: (a, b) => a.src_ip.localeCompare(b.src_ip),
      dest: (a, b) => a.dest_ip.localeCompare(b.dest_ip),
    };
    return [...rows].sort(by[sort]);
  }, [flows, ifaceFilter, protoFilter, q, portFilter, onlyRadio, onlyUnknown, sort]);

  const filtered = shown.length !== flows.length;
  const sel = "bg-slate-800 border border-slate-700 rounded text-micro text-slate-300 px-1.5 py-0.5";

  return (
    <div className="h-full flex flex-col">
      <div className="shrink-0 flex flex-wrap items-center gap-2 px-3 py-2 border-b border-slate-800">
        <span className="text-micro uppercase tracking-widest text-slate-500">Live traffic</span>
        <span className="text-micro text-slate-600 tabular-nums">
          {filtered ? `${shown.length} of ${flows.length}` : `${shown.length} active`} ·{" "}
          {totals.packets.toLocaleString()} pkt · {bytes(totals.bytes)} total
        </span>

        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="address, port, segment…"
          className={`${sel} w-44 font-mono`}
          aria-label="Filter flows"
        />
        <input
          value={portFilter}
          onChange={(e) => setPortFilter(e.target.value)}
          placeholder="port"
          inputMode="numeric"
          className={`${sel} w-16 font-mono tabular-nums`}
          aria-label="Filter by port"
        />
        <select
          value={protoFilter}
          onChange={(e) => setProtoFilter(e.target.value)}
          className={sel}
          aria-label="Filter by protocol"
        >
          <option value="all">Any proto</option>
          {protos.map((pr) => (
            <option key={pr} value={pr}>
              {pr}
            </option>
          ))}
        </select>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
          className={sel}
          aria-label="Sort flows"
        >
          <option value="idle">Most recent</option>
          <option value="rate">Fastest</option>
          <option value="packets">Most packets</option>
          <option value="bytes">Most bytes</option>
          <option value="src">Source</option>
          <option value="dest">Destination</option>
        </select>
        <label className="flex items-center gap-1 text-micro text-slate-400 cursor-pointer">
          <input type="checkbox" checked={onlyRadio} onChange={(e) => setOnlyRadio(e.target.checked)} />
          radio link only
        </label>
        <label
          className="flex items-center gap-1 text-micro text-slate-400 cursor-pointer"
          title="Flows where neither end is serving a port this lab is supposed to have"
        >
          <input type="checkbox" checked={onlyUnknown} onChange={(e) => setOnlyUnknown(e.target.checked)} />
          unknown peers
        </label>
        {(filtered || q || portFilter) && (
          <button
            onClick={() => {
              setQ("");
              setPortFilter("");
              setProtoFilter("all");
              setIfaceFilter("all");
              setOnlyRadio(false);
              setOnlyUnknown(false);
            }}
            className="text-micro px-1.5 py-0.5 rounded border border-slate-700 text-slate-400 hover:text-slate-200"
          >
            clear
          </button>
        )}

        <div className="ml-auto flex rounded overflow-hidden border border-slate-700">
          {["all", ...ifaces].map((i) => (
            <button
              key={i}
              onClick={() => setIfaceFilter(i)}
              className={`px-2 py-0.5 text-micro ${
                ifaceFilter === i ? "bg-slate-600 text-white" : "bg-slate-800 text-slate-400 hover:text-slate-200"
              }`}
            >
              {i === "all" ? "All segments" : i}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-auto">
        {shown.length === 0 ? (
          <div className="p-4 text-label text-slate-600">
            {flows.length === 0 ? (
              <>
                Nothing on the wire yet. Traffic appears as soon as the drone is powered
                on and the C2 starts talking to it.
              </>
            ) : (
              <>No flow matches those filters - {flows.length} are active.</>
            )}
          </div>
        ) : (
          <table className="w-full text-micro font-mono">
            <thead className="sticky top-0 bg-slate-900 text-slate-500">
              <tr className="text-left">
                <th className="px-3 py-1.5 font-normal">Last seen</th>
                <th className="px-3 py-1.5 font-normal">Source</th>
                <th className="px-3 py-1.5 font-normal">Destination</th>
                <th className="px-3 py-1.5 font-normal">Proto</th>
                <th className="px-3 py-1.5 font-normal">Segment</th>
                <th className="px-3 py-1.5 font-normal text-right">Packets</th>
                <th className="px-3 py-1.5 font-normal text-right">Rate</th>
                <th className="px-3 py-1.5 font-normal text-right">Bytes</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((f, i) => {
                const role = f.dest_port ? PORT_ROLE[f.dest_port] : undefined;
                const radio = f.dest_port === 14550;
                return (
                  <tr
                    key={`${f.src_ip}:${f.src_port}-${f.dest_ip}:${f.dest_port}-${f.proto}-${i}`}
                    className={`border-t border-slate-800/60 hover:bg-slate-800/40 ${
                      radio ? "bg-fuchsia-500/5" : ""
                    }`}
                  >
                    <td className="px-3 py-1 text-slate-500 tabular-nums">{ago(f.idle_s)}</td>
                    <td className="px-3 py-1 text-slate-300">
                      {f.src_ip}
                      {f.src_port != null && <span className="text-slate-600">:{f.src_port}</span>}
                    </td>
                    <td className="px-3 py-1 text-slate-300">
                      {f.dest_ip}
                      {f.dest_port != null && <span className="text-slate-600">:{f.dest_port}</span>}
                      {role && <span className="ml-1.5 text-blue-400/80">{role}</span>}
                    </td>
                    <td className="px-3 py-1 text-slate-400">{f.proto}</td>
                    <td className="px-3 py-1 text-slate-500">{f.iface}</td>
                    <td className="px-3 py-1 text-right text-slate-400 tabular-nums">
                      {f.packets.toLocaleString()}
                    </td>
                    <td className="px-3 py-1 text-right text-slate-500 tabular-nums">
                      {f.pps} /s
                    </td>
                    <td className="px-3 py-1 text-right text-slate-400 tabular-nums">
                      {bytes(f.bytes)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
