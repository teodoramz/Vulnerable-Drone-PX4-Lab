import { useEffect, useMemo, useRef, useState } from "react";

import type { LogEntry, LogLevel } from "../api/types";
import { clockGmt3 } from "../lib/time";

/** Per-level styling; `attack` is distinct from `error`. */
const LEVEL_STYLE: Record<LogLevel, { text: string; bar: string; tag: string }> = {
  info: { text: "text-slate-300", bar: "bg-slate-700", tag: "INFO" },
  cmd: { text: "text-blue-300", bar: "bg-blue-500", tag: "CMD" },
  warn: { text: "text-amber-300", bar: "bg-amber-500", tag: "WARN" },
  error: { text: "text-red-300", bar: "bg-red-500", tag: "ERR" },
  attack: { text: "text-fuchsia-300", bar: "bg-fuchsia-500", tag: "ATK" },
};

const PROBLEM_LEVELS: LogLevel[] = ["warn", "error", "attack"];

function clockOf(ts: string): string {
  // GMT+3 (see lib/time); falls back to the raw value if unparseable.
  return clockGmt3(ts);
}

export default function Terminal({ logs }: { logs: LogEntry[] }) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [problemsOnly, setProblemsOnly] = useState(false);
  const [copied, setCopied] = useState(false);

  const problemCount = useMemo(
    () => logs.filter((l) => PROBLEM_LEVELS.includes(l.level)).length,
    [logs],
  );
  const shown = useMemo(
    () => (problemsOnly ? logs.filter((l) => PROBLEM_LEVELS.includes(l.level)) : logs),
    [logs, problemsOnly],
  );

  useEffect(() => {
    const el = boxRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [shown]);

  const copy = async () => {
    const text = shown
      .map((l) => `${clockOf(l.ts)} [${LEVEL_STYLE[l.level].tag}] ${l.msg}${l.detail ? `  (${l.detail})` : ""}`)
      .join("\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked (insecure origin, permissions) - non-fatal */
    }
  };

  return (
    <div className="h-full flex flex-col rounded-xl border border-slate-800 overflow-hidden bg-black">
      <div className="shrink-0 flex items-center gap-2 px-3 py-1.5 border-b border-slate-800 bg-slate-900">
        <span className="text-micro uppercase tracking-widest text-slate-500">Terminal</span>
        <div className="ml-auto flex items-center gap-1">
          <button
            onClick={() => setProblemsOnly((v) => !v)}
            title="Show only warnings, errors and attacks"
            className={`text-micro px-1.5 py-0.5 rounded border transition-colors ${
              problemsOnly
                ? "bg-amber-500/20 border-amber-600 text-amber-300"
                : "bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200"
            }`}
          >
            Problems{problemCount > 0 ? ` (${problemCount})` : ""}
          </button>
          <button
            onClick={copy}
            title="Copy the visible log to the clipboard"
            className="text-micro px-1.5 py-0.5 rounded border bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200"
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>

      <div ref={boxRef} className="flex-1 min-h-0 overflow-y-auto font-mono text-micro">
        {shown.length === 0 && (
          <div className="p-3 text-slate-600">
            {problemsOnly ? "No warnings or errors." : "[SYSTEM] Awaiting telemetry…"}
          </div>
        )}
        {shown.map((l, i) => {
          const style = LEVEL_STYLE[l.level] ?? LEVEL_STYLE.info;
          return (
            <div key={i} className="flex gap-2 px-2 py-0.5 hover:bg-slate-900/60">
              <span className={`w-0.5 shrink-0 rounded ${style.bar}`} />
              <span className="shrink-0 text-slate-600 tabular-nums">{clockOf(l.ts)}</span>
              <span className={`shrink-0 w-8 ${style.text} opacity-80`}>{style.tag}</span>
              <span className="min-w-0 break-words">
                <span className={style.text}>{l.msg}</span>
                {l.detail && <span className="block text-slate-500">↳ {l.detail}</span>}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
