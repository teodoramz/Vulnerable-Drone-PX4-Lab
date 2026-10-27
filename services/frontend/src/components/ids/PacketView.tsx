import { useMemo, useState } from "react";

import type { PacketRow } from "../../features/ids/useTraffic";

function hexDump(hex: string): string[] {
  const bytes = hex.match(/.{1,2}/g) ?? [];
  const lines: string[] = [];
  for (let i = 0; i < bytes.length; i += 16) {
    const row = bytes.slice(i, i + 16);
    const ascii = row
      .map((b) => {
        const v = parseInt(b, 16);
        return v >= 32 && v < 127 ? String.fromCharCode(v) : ".";
      })
      .join("");
    lines.push(
      `${i.toString(16).padStart(4, "0")}  ${row.join(" ").padEnd(47, " ")}  ${ascii}`,
    );
  }
  return lines;
}

function port(p: number | null): string {
  return p === null ? "" : `:${p}`;
}

/** Recent packets, with the decoded MAVLink message where there is one. */
export default function PacketView({
  packets,
  mavlinkOnly,
  onMavlinkOnly,
  paused,
  onPaused,
}: {
  packets: PacketRow[];
  mavlinkOnly: boolean;
  onMavlinkOnly: (v: boolean) => void;
  paused: boolean;
  onPaused: (v: boolean) => void;
}) {
  const [selected, setSelected] = useState<PacketRow | null>(null);
  const [q, setQ] = useState("");
  const [msgFilter, setMsgFilter] = useState("all");
  const [protoFilter, setProtoFilter] = useState("all");
  const [minLen, setMinLen] = useState("");

  // Message types actually present, for the dropdown.
  const messages = useMemo(
    () =>
      Array.from(
        new Set(packets.map((p) => p.mavlink?.msg).filter((m): m is string => !!m)),
      ).sort(),
    [packets],
  );
  const protos = useMemo(
    () => Array.from(new Set(packets.map((p) => p.proto))).sort(),
    [packets],
  );

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const min = Number(minLen) || 0;
    return packets.filter((p) => {
      if (protoFilter !== "all" && p.proto !== protoFilter) return false;
      if (msgFilter !== "all" && p.mavlink?.msg !== msgFilter) return false;
      if (min && p.length < min) return false;
      if (needle) {
        const hay = [
          p.src_ip, p.src_port, p.dest_ip, p.dest_port, p.proto, p.iface,
          p.mavlink?.msg, p.mavlink?.command_name,
          p.mavlink?.sysid != null ? `sys${p.mavlink.sysid}` : "",
          p.ascii,
        ].join(" ").toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });
  }, [packets, q, msgFilter, protoFilter, minLen]);

  const filtered = shown.length !== packets.length;
  const sel = "bg-slate-800 border border-slate-700 rounded text-micro text-slate-300 px-1.5 py-0.5";

  return (
    <div className="h-full flex min-h-0">
      <div className="flex-[3] min-w-0 flex flex-col min-h-0 border-r border-slate-800">
        <div className="shrink-0 px-3 py-1.5 border-b border-slate-800 flex flex-wrap items-center gap-2 text-micro">
          <span className="text-slate-400 tabular-nums">
            {filtered ? `${shown.length} of ${packets.length}` : `${packets.length}`} packets
          </span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="address, port, sys255, message…"
            className={`${sel} w-48 font-mono`}
            aria-label="Filter packets"
          />
          <select
            value={msgFilter}
            onChange={(e) => setMsgFilter(e.target.value)}
            className={sel}
            aria-label="Filter by MAVLink message"
          >
            <option value="all">Any message</option>
            {messages.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <select
            value={protoFilter}
            onChange={(e) => setProtoFilter(e.target.value)}
            className={sel}
            aria-label="Filter packets by protocol"
          >
            <option value="all">Any proto</option>
            {protos.map((pr) => (
              <option key={pr} value={pr}>
                {pr}
              </option>
            ))}
          </select>
          <input
            value={minLen}
            onChange={(e) => setMinLen(e.target.value)}
            placeholder="min len"
            inputMode="numeric"
            className={`${sel} w-16 tabular-nums`}
            aria-label="Minimum packet length"
          />
          <label className="flex items-center gap-1.5 text-slate-400 cursor-pointer">
            <input
              type="checkbox"
              checked={mavlinkOnly}
              onChange={(e) => onMavlinkOnly(e.target.checked)}
            />
            MAVLink only
          </label>
          <label className="flex items-center gap-1.5 text-slate-400 cursor-pointer">
            <input type="checkbox" checked={paused} onChange={(e) => onPaused(e.target.checked)} />
            freeze
          </label>
          {(filtered || q) && (
            <button
              onClick={() => {
                setQ("");
                setMsgFilter("all");
                setProtoFilter("all");
                setMinLen("");
              }}
              className="px-1.5 py-0.5 rounded border border-slate-700 text-slate-400 hover:text-slate-200"
            >
              clear
            </button>
          )}
          <span className="ml-auto text-slate-600">click a row for the bytes</span>
        </div>

        <div className="flex-1 min-h-0 overflow-auto">
          <table className="w-full text-micro font-mono">
            <thead className="sticky top-0 bg-slate-900 text-slate-600">
              <tr className="border-b border-slate-800">
                <th className="text-left font-medium px-2 py-1">Time</th>
                <th className="text-left font-medium px-2 py-1">Source</th>
                <th className="text-left font-medium px-2 py-1">Destination</th>
                <th className="text-left font-medium px-2 py-1">Proto</th>
                <th className="text-right font-medium px-2 py-1">Len</th>
                <th className="text-left font-medium px-2 py-1">MAVLink</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((p, i) => {
                const chosen = selected
                  ? selected.ts === p.ts && selected.hex === p.hex
                  : false;
                return (
                  <tr
                    key={`${p.ts}-${i}`}
                    onClick={() => setSelected(p)}
                    className={`border-b border-slate-800/50 cursor-pointer ${
                      chosen ? "bg-slate-800" : "hover:bg-slate-850"
                    }`}
                  >
                    <td className="px-2 py-0.5 text-slate-500">
                      {p.ts.slice(11, 23)}
                    </td>
                    <td className="px-2 py-0.5 text-slate-300">
                      {p.src_ip}
                      <span className="text-slate-500">{port(p.src_port)}</span>
                    </td>
                    <td className="px-2 py-0.5 text-slate-300">
                      {p.dest_ip}
                      <span className="text-slate-500">{port(p.dest_port)}</span>
                    </td>
                    <td className="px-2 py-0.5 text-slate-400">{p.proto}</td>
                    <td className="px-2 py-0.5 text-right text-slate-400 tabular-nums">
                      {p.length}
                    </td>
                    <td className="px-2 py-0.5">
                      {p.mavlink ? (
                        <span className="text-cyan-300">
                          {p.mavlink.msg}
                          {p.mavlink.command_name && (
                            <span className="text-amber-300">/{p.mavlink.command_name}</span>
                          )}
                          <span className="text-slate-600">
                            {" "}
                            v{p.mavlink.version} sys{p.mavlink.sysid}
                          </span>
                        </span>
                      ) : (
                        <span className="text-slate-700">-</span>
                      )}
                    </td>
                  </tr>
                );
              })}
              {shown.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-center text-slate-600">
                    {packets.length === 0 ? (
                      <>
                        Nothing captured yet.
                        {mavlinkOnly && " No MAVLink in the ring - untick “MAVLink only”."}
                      </>
                    ) : (
                      <>No packet matches those filters - {packets.length} in the ring.</>
                    )}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex-[2] min-w-[20rem] flex flex-col min-h-0">
        {selected ? (
          <>
            <div className="shrink-0 px-3 py-2 border-b border-slate-800">
              <div className="text-xs text-slate-200 font-mono">
                {selected.src_ip}
                {port(selected.src_port)} → {selected.dest_ip}
                {port(selected.dest_port)}
              </div>
              <div className="text-micro text-slate-500 mt-0.5">
                {selected.proto} · {selected.length} bytes · {selected.iface} ·{" "}
                {selected.ts.slice(11, 23)}
              </div>
              {selected.mavlink && (
                <div className="mt-1.5 text-micro">
                  <span className="text-cyan-300 font-semibold">{selected.mavlink.msg}</span>
                  {selected.mavlink.command_name && (
                    <span className="text-amber-300"> / {selected.mavlink.command_name}</span>
                  )}
                  <div className="text-slate-500 mt-0.5 tabular-nums">
                    msg id {selected.mavlink.msg_id} · seq {selected.mavlink.seq} · system{" "}
                    {selected.mavlink.sysid} · component {selected.mavlink.compid} · MAVLink v
                    {selected.mavlink.version}
                  </div>
                </div>
              )}
            </div>
            <div className="flex-1 min-h-0 overflow-auto p-3">
              <div className="text-micro uppercase tracking-widest text-slate-600 mb-1">
                Payload (first bytes)
              </div>
              <pre className="text-micro font-mono text-slate-300 leading-relaxed whitespace-pre">
                {hexDump(selected.hex).join("\n") || "(no payload)"}
              </pre>
            </div>
          </>
        ) : (
          <div className="p-3 text-micro text-slate-500 leading-relaxed">
            Select a packet to see its bytes.
            <div className="mt-2 text-slate-600">
              The sensor keeps the first 64 bytes of each payload - enough to identify a
              MAVLink message and see its header. For whole packets, download a capture from
              the Captures view.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
