import type { BadgeTone } from "../ui/Badge";

/** severity: 1 = high, 2 = medium, 3 = low (fixed contract with the sensor). */
export function severityLabel(sev: number): string {
  if (sev === 1) return "HIGH";
  if (sev === 2) return "MEDIUM";
  return "LOW";
}

export function severityTone(sev: number): BadgeTone {
  if (sev === 1) return "danger";
  if (sev === 2) return "warning";
  return "info";
}

export function severityBorder(sev: number): string {
  if (sev === 1) return "border-l-red-500";
  if (sev === 2) return "border-l-amber-500";
  return "border-l-blue-500";
}
