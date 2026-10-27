import type { LatLon } from "./geo";

/** Site definition fetched from the C2 (`GET /api/site`). Not duplicated locally, so the drawn boundary is the one the C2 enforces. All coordinates are real lat/lon. */
export interface PatrolRoute {
  name: string;
  description: string;
  /** [lat, lon] pairs. */
  points: [number, number][];
}

export interface LaunchPad {
  id: string;
  designator: string | null;
  lat: number;
  lon: number;
  diameter_m: number;
  grid_ref: string | null;
}

export interface ObjectTypeInfo {
  type: string;
  count: number;
  scenery: boolean;
  max_height_m: number;
}

/** One object from the site dataset. Only `id`/`type`/position/size are guaranteed; the rest depends on the type. */
export interface SiteObject {
  id: string;
  type: string;
  lat: number;
  lon: number;
  px: [number, number];
  length_m: number;
  width_m: number;
  height_m: number;
  grid_ref?: string | null;
  heading_deg?: number;
  footprint_latlon?: [number, number][];
  path_latlon?: [number, number][];
  color_hex?: string;
  use?: string;
  designator?: string;
  species?: string;
  model?: string;
  stand?: string;
  road_class?: string;
  surface?: string;
  crop?: string;
  note?: string;
  inside_operational_area?: boolean;
  /** Metres from the searched position to this footprint; present on proximity searches only. 0 means inside. */
  distance_m?: number;
  [key: string]: unknown;
}

export interface SiteDef {
  image: string;
  name: string;
  image_size_px: [number, number];
  meters_per_pixel: number;
  map_width_m: number;
  map_height_m: number;
  bounds: { south: number; west: number; north: number; east: number };
  boundary: [number, number][];
  boundary_area_km2: number;
  grid: { cell_size_m: number; columns: string[]; rows: string[] };
  launch_pads: LaunchPad[];
  default_pad: string;
  pad_radius_m: number;
  home_lat: number;
  home_lon: number;
  default_route: string;
  routes: Record<string, PatrolRoute>;
  object_types: ObjectTypeInfo[];
  total_objects: number;
  scenery_types: string[];
}

/** What a click on the map found (`GET /api/site/objects/at`). */
export interface PointLookup {
  lat: number;
  lon: number;
  grid_ref: string | null;
  inside_operational_area: boolean;
  metres_outside_area?: number;
  objects: SiteObject[];
  alt?: number;
  would_hit?: SiteObject | null;
}

export interface ObjectPage {
  total: number;
  offset: number;
  limit: number;
  objects: SiteObject[];
}

const METERS_PER_DEG_LAT = 111320.0;

/** Metres per degree of longitude at the site's latitude. */
export function metresPerDegLon(lat: number): number {
  return METERS_PER_DEG_LAT * Math.cos((lat * Math.PI) / 180);
}

export function metresBetween(a: LatLon, b: LatLon): number {
  const dy = (a.lat - b.lat) * METERS_PER_DEG_LAT;
  const dx = (a.lon - b.lon) * metresPerDegLon(a.lat);
  return Math.hypot(dx, dy);
}

/** The lat/lon rectangle the map image occupies, as Leaflet wants it:
 *  [[south, west], [north, east]]. */
export function imageBounds(site: SiteDef): [[number, number], [number, number]] {
  const b = site.bounds;
  return [
    [b.south, b.west],
    [b.north, b.east],
  ];
}

export function boundaryLatLon(site: SiteDef): [number, number][] {
  return site.boundary;
}

/** A predefined route as world coordinates. */
export function routeLatLon(site: SiteDef, key: string): LatLon[] {
  const route = site.routes[key];
  if (!route) return [];
  return route.points.map(([lat, lon]) => ({ lat, lon }));
}

/** An object's outline for drawing. Handles the three dataset shapes (polygon, centreline with width, centre plus size and heading) so it matches the C2's footprint test. */
export function outline(o: SiteObject): [number, number][] {
  if (o.footprint_latlon?.length) return o.footprint_latlon;
  if (o.path_latlon?.length) return o.path_latlon;

  const halfL = o.length_m / 2;
  const halfW = o.width_m / 2;
  const theta = ((o.heading_deg ?? 0) * Math.PI) / 180;
  // Along-heading unit vector in (east, north); heading 0 is north.
  const ae = Math.sin(theta);
  const an = Math.cos(theta);
  // Across-heading is that rotated 90 degrees.
  const ce = Math.cos(theta);
  const cn = -Math.sin(theta);
  const mLon = metresPerDegLon(o.lat);
  return ([
    [1, 1],
    [1, -1],
    [-1, -1],
    [-1, 1],
  ] as const).map(([sl, sw]) => {
    const east = sl * halfL * ae + sw * halfW * ce;
    const north = sl * halfL * an + sw * halfW * cn;
    return [o.lat + north / METERS_PER_DEG_LAT, o.lon + east / mLon] as [number, number];
  });
}

/** True when an object is drawn as a line rather than a closed shape. */
export function isPath(o: SiteObject): boolean {
  return !o.footprint_latlon?.length && !!o.path_latlon?.length;
}

/** Colour per object type; the dataset's `color_hex` wins where present. */
const TYPE_COLOR: Record<string, string> = {
  control_tower: "#ff9f43",
  transmission_pylon: "#ff6b6b",
  power_line: "#ff6b6b",
  radar_mast: "#ff9f43",
  glide_slope_mast: "#ff9f43",
  localizer_antenna: "#ff9f43",
  windsock_mast: "#ff9f43",
  vor_beacon: "#ff9f43",
  grain_silo: "#e8a33d",
  fuel_tank: "#e8a33d",
  building: "#d6b36a",
  aircraft: "#7cc4e8",
  helicopter: "#7cc4e8",
  runway: "#6b7280",
  taxiway: "#6b7280",
  apron: "#6b7280",
  road: "#9aa5b1",
  bridge: "#9aa5b1",
  railway_track: "#8b8b8b",
  security_fence: "#a78bfa",
  fence: "#a78bfa",
  river: "#3b82f6",
  lake: "#3b82f6",
  stormwater_pond: "#3b82f6",
  tree: "#4ade80",
  agricultural_field: "#a3a35c",
  solar_panel_table: "#60a5fa",
  helipad: "#3fbfae",
};

export function objectColor(o: SiteObject): string {
  if (typeof o.color_hex === "string") return o.color_hex;
  return TYPE_COLOR[o.type] ?? "#cbd5e1";
}

/** A readable name for an object: the most specific dataset field, else a tidied type. */
export function objectLabel(o: SiteObject): string {
  const specific = o.designator || o.use || o.model || o.species || o.road_class || o.name;
  const kind = prettyType(o.type);
  return typeof specific === "string" && specific ? `${kind} - ${specific}` : kind;
}

export function prettyType(type: string): string {
  const s = type.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}
