import type { ReactNode } from "react";

/** Shared styling for every text/number input. */
export const inputClass =
  "bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-100 outline-none focus:border-blue-500 disabled:opacity-40 disabled:cursor-not-allowed";

/** A labeled control row: `Label [ control(s) ]`. */
export default function Field({
  label,
  labelWidth = "w-16",
  children,
}: {
  label: string;
  labelWidth?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex items-center gap-2">
      <label className={`text-xs text-slate-400 shrink-0 ${labelWidth}`}>{label}</label>
      {children}
    </div>
  );
}
