import L from "leaflet";

// Shared geometry helpers (metre offsets from a geo centre): north = +metres north, east = +metres east.
// Every map layer draws with these, so keep them simple.

export interface LatLon {
  lat: number;
  lon: number;
}

/** Offset a centre point by (n) metres north and (e) metres east. */
export function offset(c: LatLon, n: number, e: number): [number, number] {
  return [c.lat + n / 111320.0, c.lon + e / (111320.0 * Math.cos((c.lat * Math.PI) / 180))];
}

/** Axis-aligned rectangle from north/south and east/west extents (metres). */
export function rect(c: LatLon, nMax: number, nMin: number, eMin: number, eMax: number): [number, number][] {
  return [offset(c, nMax, eMin), offset(c, nMax, eMax), offset(c, nMin, eMax), offset(c, nMin, eMin)];
}

/** Map a list of (n, e) metre pairs to lat/lon around a centre. */
export function poly(c: LatLon, pts: [number, number][]): [number, number][] {
  return pts.map(([n, e]) => offset(c, n, e));
}

/** Rotated strip of half-width hw from (n0,e0) -> (n1,e1) - roads, channels, runways. */
export function strip(c: LatLon, n0: number, e0: number, n1: number, e1: number, hw: number): [number, number][] {
  const dn = n1 - n0,
    de = e1 - e0,
    len = Math.hypot(dn, de) || 1;
  const pn = (-de / len) * hw,
    pe = (dn / len) * hw;
  return [offset(c, n0 + pn, e0 + pe), offset(c, n1 + pn, e1 + pe), offset(c, n1 - pn, e1 - pe), offset(c, n0 - pn, e0 - pe)];
}

/** Arc of radius r (metres) around a local (cn, ce) centre, from angle a0 to a1 (degrees, 0 = east, 90 = north). */
export function arc(cn: number, ce: number, r: number, a0: number, a1: number, steps = 16): [number, number][] {
  const out: [number, number][] = [];
  for (let i = 0; i <= steps; i++) {
    const a = ((a0 + ((a1 - a0) * i) / steps) * Math.PI) / 180;
    out.push([cn + r * Math.cos(a), ce + r * Math.sin(a)]);
  }
  return out;
}

/** Closed circle polygon of radius r (metres) around a local (cn, ce) centre. */
export function circle(cn: number, ce: number, r: number, steps = 32): [number, number][] {
  return arc(cn, ce, r, 0, 360, steps).slice(0, -1);
}

/** Small monospace text label rendered as a divIcon (no marker chrome). */
export function label(text: string, color = "#cbd5e1", size = 11) {
  return L.divIcon({
    className: "",
    html: `<div style="color:${color};font:700 ${size}px/1 ui-monospace,monospace;letter-spacing:.05em;text-shadow:0 0 3px #000;white-space:nowrap">${text}</div>`,
    iconSize: [1, 1],
  });
}
