import { useEffect, useState } from "react";

import api from "../api/client";
import type { AuditEntry } from "../api/types";
import { stampGmt3 } from "../lib/time";

export default function Audit() {
  const [rows, setRows] = useState<AuditEntry[]>([]);

  useEffect(() => {
    api.get<AuditEntry[]>("/api/audit").then((r) => setRows(r.data)).catch(() => {});
  }, []);

  return (
    <div className="h-full overflow-auto p-6">
      <h1 className="text-xl font-bold mb-4 text-slate-100">Audit Log</h1>
      <table className="w-full text-xs border border-slate-800 rounded-xl overflow-hidden">
        <thead className="bg-slate-900 text-slate-400">
          <tr>
            <th className="text-left p-2">Time (GMT+3)</th>
            <th className="text-left p-2">User</th>
            <th className="text-left p-2">Drone</th>
            <th className="text-left p-2">Action</th>
            <th className="text-left p-2">Result</th>
            <th className="text-left p-2">Params</th>
          </tr>
        </thead>
        <tbody className="font-mono">
          {rows.map((r) => (
            <tr key={r.id} className="border-t border-slate-800">
              <td className="p-2 text-slate-500 whitespace-nowrap">{stampGmt3(r.ts)}</td>
              <td className="p-2">{r.username || "-"}</td>
              <td className="p-2 text-slate-400">{r.drone_id ?? "-"}</td>
              <td className="p-2 font-bold">{r.action}</td>
              <td className="p-2">
                <span className={r.result === "denied" ? "text-red-400" : "text-emerald-400"}>{r.result}</span>
              </td>
              <td className="p-2 text-slate-500">
                {Object.keys(r.params).length ? JSON.stringify(r.params) : ""}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={6} className="p-4 text-center text-slate-600">
                No audit entries yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
