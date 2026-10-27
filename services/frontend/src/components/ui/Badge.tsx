import type { ReactNode } from "react";

export type BadgeTone = "neutral" | "success" | "danger" | "warning" | "info" | "purple";

const TONE_CLASS: Record<BadgeTone, string> = {
  neutral: "bg-slate-700 text-slate-300",
  success: "bg-emerald-600/30 text-emerald-300 border border-emerald-700",
  danger: "bg-red-600/30 text-red-200 border border-red-700",
  warning: "bg-amber-600/20 text-amber-300 border border-amber-700",
  info: "bg-blue-600/20 text-blue-300 border border-blue-700",
  purple: "bg-purple-500/20 text-purple-300 border border-purple-600",
};

/** Small status pill - connection state, claim state, role, severity, etc. */
export default function Badge({
  tone = "neutral",
  pulse = false,
  className = "",
  children,
}: {
  tone?: BadgeTone;
  pulse?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 text-label px-2 py-0.5 rounded-full font-semibold whitespace-nowrap ${TONE_CLASS[tone]} ${pulse ? "animate-pulse" : ""} ${className}`}
    >
      {children}
    </span>
  );
}
