import type { IdsAlert } from "../../api/types";
import Badge from "../ui/Badge";
import { severityLabel, severityTone } from "./severity";
import { stampGmt3 } from "../../lib/time";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1 border-b border-slate-800/70">
      <span className="text-label text-slate-500">{label}</span>
      <span className="text-xs text-slate-200 font-mono text-right break-all">{value}</span>
    </div>
  );
}

export default function AlertDetail({ alert }: { alert: IdsAlert | null }) {
  if (!alert) {
    return (
      <div className="h-full flex items-center justify-center text-label text-slate-600 p-4 text-center">
        Select an alert to inspect it.
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="text-sm font-bold text-slate-100">{alert.signature}</span>
        <Badge tone={severityTone(alert.severity)}>{severityLabel(alert.severity)}</Badge>
      </div>
      <Row label="Time (GMT+3)" value={stampGmt3(alert.ts)} />
      <Row label="Category" value={alert.category} />
      <Row label="SID" value={String(alert.sid)} />
      <Row label="Source" value={`${alert.src_ip}:${alert.src_port}`} />
      <Row label="Destination" value={`${alert.dest_ip}:${alert.dest_port}`} />
      <Row label="Protocol" value={alert.proto} />
      <Row label="Interface" value={alert.iface} />

      <PacketBytes alert={alert} />
    </div>
  );
}

/** The bytes that tripped the rule; the MAVLink 2 header is annotated. */
function PacketBytes({ alert }: { alert: IdsAlert }) {
  if (!alert.payload) {
    return (
      <div className="mt-3 pt-3 border-t border-slate-800 text-micro text-slate-600">
        No packet bytes recorded for this alert. Suricata payload logging must be enabled
        (eve-log → alert → payload) for the sensor to carry them.
      </div>
    );
  }

  let raw: Uint8Array;
  try {
    const bin = atob(alert.payload);
    raw = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  } catch {
    return (
      <div className="mt-3 pt-3 border-t border-slate-800 text-micro text-red-400">
        Packet bytes were not valid base64 and could not be decoded.
      </div>
    );
  }

  const hex = Array.from(raw, (b) => b.toString(16).padStart(2, "0"));
  const rows: string[][] = [];
  for (let i = 0; i < hex.length; i += 16) rows.push(hex.slice(i, i + 16));

  // MAVLink 2: 0xFD magic, len, incompat, compat, seq, sysid, compid, then a 24-bit little-endian message id.
  const isMavlink2 = raw.length >= 10 && raw[0] === 0xfd;
  const msgId = isMavlink2 ? raw[7] | (raw[8] << 8) | (raw[9] << 16) : null;

  return (
    <div className="mt-3 pt-3 border-t border-slate-800">
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-micro uppercase tracking-widest text-slate-500">Packet bytes</span>
        <span className="text-micro text-slate-600">{raw.length} bytes</span>
      </div>

      {isMavlink2 && (
        <div className="mb-2 text-micro font-mono text-slate-400">
          MAVLink 2 · sysid <span className="text-blue-300">{raw[5]}</span> · compid{" "}
          <span className="text-blue-300">{raw[6]}</span> · msgid{" "}
          <span className="text-blue-300">{msgId}</span> · payload{" "}
          <span className="text-blue-300">{raw[1]}</span> B
        </div>
      )}

      <div className="rounded border border-slate-800 bg-black p-2 overflow-x-auto">
        <table className="font-mono text-micro">
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                <td className="pr-3 text-slate-600 select-none tabular-nums">
                  {(i * 16).toString(16).padStart(4, "0")}
                </td>
                {row.map((b, j) => {
                  const off = i * 16 + j;
                  // Highlight the header fields so they can be picked out.
                  const header = isMavlink2 && off < 10;
                  return (
                    <td
                      key={j}
                      className={`pr-1 ${header ? "text-fuchsia-300" : "text-green-400"}`}
                    >
                      {b}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {alert.payload_printable && (
        <pre className="mt-2 rounded border border-slate-800 bg-black p-2 text-micro font-mono text-slate-400 whitespace-pre-wrap break-all max-h-40 overflow-y-auto">
          {alert.payload_printable}
        </pre>
      )}
    </div>
  );
}
