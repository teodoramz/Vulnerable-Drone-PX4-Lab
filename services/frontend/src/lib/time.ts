// Display timezone: the range runs on GMT+3 while the API emits UTC, so times shift by a fixed +3h (no DST).
export const DISPLAY_TZ_LABEL = "GMT+3";

const OFFSET_MS = 3 * 60 * 60 * 1000;

// Parse a backend timestamp as UTC even without an explicit zone.
function parseUtc(ts: string | number | Date): Date {
  if (ts instanceof Date) return ts;
  if (typeof ts === "number") return new Date(ts);
  const hasZone = /([zZ])$|[+-]\d{2}:?\d{2}$/.test(ts);
  return new Date(hasZone ? ts : ts + "Z");
}

// HH:MM:SS in GMT+3.
export function clockGmt3(ts: string | number | Date): string {
  const d = parseUtc(ts);
  if (Number.isNaN(d.getTime())) return typeof ts === "string" ? ts.slice(11, 19) : "";
  return new Date(d.getTime() + OFFSET_MS).toISOString().slice(11, 19);
}

// YYYY-MM-DD HH:MM:SS in GMT+3.
export function stampGmt3(ts: string | number | Date): string {
  const d = parseUtc(ts);
  if (Number.isNaN(d.getTime())) return typeof ts === "string" ? ts.replace("T", " ").slice(0, 19) : "";
  return new Date(d.getTime() + OFFSET_MS).toISOString().replace("T", " ").slice(0, 19);
}
