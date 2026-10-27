"""Site geometry, loaded from `app/data/airport_objects.json`.

Objects, boundary polygon, launch pads, patrol routes and the map projection.
The console draws what this module serves, so what is shown is what is enforced.
"""
from __future__ import annotations

import json
import math
import pathlib
from functools import lru_cache
from typing import Any, Iterable

DATA_FILE = pathlib.Path(__file__).resolve().parent.parent / "data" / "airport_objects.json"

with DATA_FILE.open() as fh:
    _DATA: dict[str, Any] = json.load(fh)

MAP: dict[str, Any] = _DATA["map"]
OBJECTS: list[dict[str, Any]] = _DATA["objects"]
GRID: dict[str, Any] = _DATA["grid"]

# The dataset title is a file description, so the site is named here.
SITE_NAME = "Marwick International Airport"
DATASET_TITLE: str = MAP["title"]
IMAGE_PATH = "/map/airport.jpg"

IMAGE_W_PX, IMAGE_H_PX = MAP["image_size_px"]
M_PER_PX: float = MAP["meters_per_pixel"]
MAP_WIDTH_M, MAP_HEIGHT_M = MAP["covered_area_m"]

ORIGIN_LAT: float = MAP["origin_lat"]
ORIGIN_LON: float = MAP["origin_lon"]
ORIGIN_PX, ORIGIN_PY = MAP["origin_pixel"]

# Flat-earth affine projection with cos() taken once at the origin latitude,
# matching the dataset exactly.
M_PER_DEG_LAT = 111320.0
M_PER_DEG_LON = 111320.0 * math.cos(math.radians(ORIGIN_LAT))

# Image corners, for the map overlay.
_CORNERS = MAP["image_corners_latlon"]
NORTH_LAT: float = _CORNERS["top_left"][0]
SOUTH_LAT: float = _CORNERS["bottom_left"][0]
WEST_LON: float = _CORNERS["top_left"][1]
EAST_LON: float = _CORNERS["top_right"][1]

BOUNDARY: list[tuple[float, float]] = [
    (lat, lon) for lat, lon in _DATA["operational_area"]["boundary_latlon"]
]
BOUNDARY_AREA_KM2: float = _DATA["operational_area"]["area_km2"]


# ── projection ───────────────────────────────────────────

def to_latlon(px: float, py: float) -> tuple[float, float]:
    """Pixel position in the map image to coordinates."""
    lat = ORIGIN_LAT - (py - ORIGIN_PY) * M_PER_PX / M_PER_DEG_LAT
    lon = ORIGIN_LON + (px - ORIGIN_PX) * M_PER_PX / M_PER_DEG_LON
    return lat, lon


def to_pixel(lat: float, lon: float) -> tuple[float, float]:
    """Inverse of :func:`to_latlon`."""
    px = ORIGIN_PX + (lon - ORIGIN_LON) * M_PER_DEG_LON / M_PER_PX
    py = ORIGIN_PY - (lat - ORIGIN_LAT) * M_PER_DEG_LAT / M_PER_PX
    return px, py


def metres_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dy = (lat1 - lat2) * M_PER_DEG_LAT
    dx = (lon1 - lon2) * M_PER_DEG_LON
    return math.hypot(dx, dy)


def offset_latlon(lat: float, lon: float, north_m: float, east_m: float) -> tuple[float, float]:
    return lat + north_m / M_PER_DEG_LAT, lon + east_m / M_PER_DEG_LON


# ── launch pads ──────────────────────────────────────────
# The drone launches from a helipad only.

LAUNCH_PADS: list[dict[str, Any]] = sorted(
    (o for o in OBJECTS if o["type"] == "helipad"),
    key=lambda o: o.get("designator", ""),
)
PAD_BY_DESIGNATOR: dict[str, dict[str, Any]] = {
    p["designator"]: p for p in LAUNCH_PADS if p.get("designator")
}
DEFAULT_PAD = "HP-1"

# Launch radius (m) around a pad centre; pads are 24 m across.
PAD_RADIUS_M = 15.0

HOME_LAT: float = PAD_BY_DESIGNATOR[DEFAULT_PAD]["lat"]
HOME_LON: float = PAD_BY_DESIGNATOR[DEFAULT_PAD]["lon"]


def pad(designator: str) -> dict[str, Any] | None:
    return PAD_BY_DESIGNATOR.get(designator)


def in_launch_area(lat: float, lon: float) -> dict[str, Any] | None:
    """The pad this position is on, or None."""
    for p in LAUNCH_PADS:
        if metres_between(lat, lon, p["lat"], p["lon"]) <= PAD_RADIUS_M:
            return p
    return None


# ── object footprints ────────────────────────────────────
# Footprint shapes in the data:
#   footprint_latlon  explicit polygon (buildings, runways, water)
#   path_latlon       centreline with a width (roads, fences, power lines)
#   neither           centre, length, width and heading
#
# Objects below this height (m) cannot be collided with.
MIN_OBSTACLE_HEIGHT_M = 0.5

# Terrain that stays in the inventory but cannot destroy an aircraft.
NON_COLLIDABLE_TYPES = {"agricultural_field"}


def _rotated_box(o: dict[str, Any]) -> list[tuple[float, float]]:
    """Corners of a box given by centre, size and compass heading (length runs along it)."""
    half_l = o["length_m"] / 2.0
    half_w = o["width_m"] / 2.0
    theta = math.radians(o.get("heading_deg", 0.0))
    # Along-heading unit vector in (east, north).
    ae, an = math.sin(theta), math.cos(theta)
    # Across-heading.
    ce, cn = math.cos(theta), -math.sin(theta)
    corners = []
    for sl, sw in ((1, 1), (1, -1), (-1, -1), (-1, 1)):
        east = sl * half_l * ae + sw * half_w * ce
        north = sl * half_l * an + sw * half_w * cn
        corners.append(offset_latlon(o["lat"], o["lon"], north, east))
    return corners


def _point_in_polygon(lat: float, lon: float, poly: Iterable[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test, in degrees."""
    pts = list(poly)
    inside = False
    n = len(pts)
    for i in range(n):
        y1, x1 = pts[i]
        y2, x2 = pts[(i + 1) % n]
        if (y1 > lat) != (y2 > lat):
            xi = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < xi:
                inside = not inside
    return inside


def _distance_to_path_m(lat: float, lon: float, path: list[list[float]]) -> float:
    """Shortest distance from a point to a polyline, in metres."""
    best = float("inf")
    for i in range(len(path) - 1):
        ay, ax = path[i]
        by, bx = path[i + 1]
        # Metres relative to the point.
        pax, pay = (ax - lon) * M_PER_DEG_LON, (ay - lat) * M_PER_DEG_LAT
        pbx, pby = (bx - lon) * M_PER_DEG_LON, (by - lat) * M_PER_DEG_LAT
        dx, dy = pbx - pax, pby - pay
        seg = dx * dx + dy * dy
        if seg == 0.0:
            best = min(best, math.hypot(pax, pay))
            continue
        t = max(0.0, min(1.0, -(pax * dx + pay * dy) / seg))
        best = min(best, math.hypot(pax + t * dx, pay + t * dy))
    return best


def contains(o: dict[str, Any], lat: float, lon: float) -> bool:
    """Whether a position falls within this object's footprint."""
    if "footprint_latlon" in o:
        return _point_in_polygon(lat, lon, [tuple(p) for p in o["footprint_latlon"]])
    if "path_latlon" in o:
        return _distance_to_path_m(lat, lon, o["path_latlon"]) <= max(o["width_m"], 1.0) / 2.0
    return _point_in_polygon(lat, lon, _rotated_box(o))


def _distance_to_footprint_m(o: dict[str, Any], lat: float, lon: float) -> float:
    """Shortest distance (m) from a point to an object's outline; callers check `contains` first."""
    if "footprint_latlon" in o:
        ring = [list(p) for p in o["footprint_latlon"]]
        return _distance_to_path_m(lat, lon, ring + [ring[0]])
    if "path_latlon" in o:
        return max(
            0.0,
            _distance_to_path_m(lat, lon, o["path_latlon"]) - max(o["width_m"], 1.0) / 2.0,
        )
    box = [list(p) for p in _rotated_box(o)]
    return _distance_to_path_m(lat, lon, box + [box[0]])


def bbox(o: dict[str, Any]) -> tuple[float, float, float, float]:
    """(south, west, north, east) bounding box, cached per object."""
    cached = o.get("_bbox")
    if cached is not None:
        return cached
    if "footprint_latlon" in o:
        pts = [(p[0], p[1]) for p in o["footprint_latlon"]]
    elif "path_latlon" in o:
        pts = [(p[0], p[1]) for p in o["path_latlon"]]
        # Pad by half the path width.
        pad_m = max(o["width_m"], 1.0) / 2.0
        lats = [p[0] for p in pts]
        lons = [p[1] for p in pts]
        box = (
            min(lats) - pad_m / M_PER_DEG_LAT, min(lons) - pad_m / M_PER_DEG_LON,
            max(lats) + pad_m / M_PER_DEG_LAT, max(lons) + pad_m / M_PER_DEG_LON,
        )
        o["_bbox"] = box
        return box
    else:
        pts = _rotated_box(o)
    lats = [p[0] for p in pts]
    lons = [p[1] for p in pts]
    box = (min(lats), min(lons), max(lats), max(lons))
    o["_bbox"] = box
    return box


# ── spatial index ────────────────────────────────────────
# Uniform grid over the map; each cell lists objects whose bbox overlaps it.

CELL_M = 100.0
_CELL_LAT = CELL_M / M_PER_DEG_LAT
_CELL_LON = CELL_M / M_PER_DEG_LON


def _cells_for(box: tuple[float, float, float, float]) -> Iterable[tuple[int, int]]:
    s, w, n, e = box
    for iy in range(int(math.floor(s / _CELL_LAT)), int(math.floor(n / _CELL_LAT)) + 1):
        for ix in range(int(math.floor(w / _CELL_LON)), int(math.floor(e / _CELL_LON)) + 1):
            yield ix, iy


def _build_index() -> dict[tuple[int, int], list[dict[str, Any]]]:
    idx: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for o in OBJECTS:
        box = bbox(o)
        # Skip map-spanning flat objects (river, solar farm).
        cells = list(_cells_for(box))
        if len(cells) > 4000:
            continue
        for cell in cells:
            idx.setdefault(cell, []).append(o)
    return idx


_INDEX = _build_index()


def _candidates(lat: float, lon: float) -> list[dict[str, Any]]:
    cell = (int(math.floor(lon / _CELL_LON)), int(math.floor(lat / _CELL_LAT)))
    return _INDEX.get(cell, [])


def objects_at(lat: float, lon: float) -> list[dict[str, Any]]:
    """Every object whose footprint covers this position, tallest first."""
    hits = [o for o in _candidates(lat, lon) if contains(o, lat, lon)]
    hits.sort(key=lambda o: -o["height_m"])
    return hits


def obstacle_at(lat: float, lon: float, alt_m: float) -> dict[str, Any] | None:
    """The object the drone would hit here at this altitude, if any."""
    for o in objects_at(lat, lon):
        if o["type"] in NON_COLLIDABLE_TYPES:
            continue
        if o["height_m"] >= MIN_OBSTACLE_HEIGHT_M and alt_m <= o["height_m"]:
            return o
    return None


# ── operational area ─────────────────────────────────────

def inside_boundary(lat: float, lon: float) -> bool:
    return _point_in_polygon(lat, lon, BOUNDARY)


def distance_outside_m(lat: float, lon: float) -> float:
    """How far beyond the boundary a position is, in metres. 0 if inside."""
    if inside_boundary(lat, lon):
        return 0.0
    ring = [list(p) for p in BOUNDARY] + [list(BOUNDARY[0])]
    return _distance_to_path_m(lat, lon, ring)


# ── grid reference ───────────────────────────────────────
# The dataset's 500 m lettered grid.

_GRID_CELL_M: float = GRID["cell_size_m"]
_GRID_COLS: list[str] = GRID["columns"]
_GRID_ROWS: list[str] = GRID["rows"]


def grid_ref(lat: float, lon: float) -> str | None:
    """The 500 m grid cell a position falls in, e.g. "E4"."""
    px, py = to_pixel(lat, lon)
    col = int(px * M_PER_PX // _GRID_CELL_M)
    row = int(py * M_PER_PX // _GRID_CELL_M)
    if 0 <= col < len(_GRID_COLS) and 0 <= row < len(_GRID_ROWS):
        return f"{_GRID_COLS[col]}{_GRID_ROWS[row]}"
    return None


# ── patrol routes ────────────────────────────────────────
# Closed loops derived from dataset features; tests check each stays inside
# the operational area and clears structures at patrol altitude.

def _inset_boundary(fraction: float) -> list[tuple[float, float]]:
    """The operational area scaled towards its centroid, to keep patrols off the boundary."""
    clat = sum(p[0] for p in BOUNDARY) / len(BOUNDARY)
    clon = sum(p[1] for p in BOUNDARY) / len(BOUNDARY)
    return [
        (clat + (lat - clat) * fraction, clon + (lon - clon) * fraction)
        for lat, lon in BOUNDARY
    ]


def _runway_circuit() -> list[tuple[float, float]]:
    """A loop around both runways, from their stated thresholds."""
    runways = sorted(
        (o for o in OBJECTS if o["type"] == "runway" and "thresholds" in o),
        key=lambda o: -o["length_m"],
    )[:2]
    pts: list[tuple[float, float]] = []
    for i, rw in enumerate(runways):
        ends = [tuple(v) for v in rw["thresholds"].values()]
        # Alternate direction so the loop does not double back.
        pts.extend(ends if i % 2 == 0 else list(reversed(ends)))
    return pts


def _apron_circuit() -> list[tuple[float, float]]:
    """A tight loop over the terminal, the stands and the parked aircraft."""
    terminal = next(
        (o for o in OBJECTS if o["type"] == "building" and o.get("use") == "passenger terminal"),
        None,
    )
    if terminal is None:
        return _inset_boundary(0.4)
    half_l = terminal["length_m"] / 2.0 + 150.0
    half_w = terminal["width_m"] / 2.0 + 220.0
    return [
        offset_latlon(terminal["lat"], terminal["lon"], north, east)
        for north, east in (
            (half_w, -half_l), (half_w, half_l), (-half_w, half_l), (-half_w, -half_l),
        )
    ]


def _approach_corridor() -> list[tuple[float, float]]:
    """Out along the main runway centreline, covering both approaches."""
    rw = max(
        (o for o in OBJECTS if o["type"] == "runway" and "thresholds" in o),
        key=lambda o: o["length_m"],
    )
    ends = [tuple(v) for v in rw["thresholds"].values()]
    (lat_a, lon_a), (lat_b, lon_b) = ends
    # Extend past each threshold, then offset sideways to close the loop.
    out_m = 600.0
    bearing_e = (lon_b - lon_a) * M_PER_DEG_LON
    bearing_n = (lat_b - lat_a) * M_PER_DEG_LAT
    length = math.hypot(bearing_e, bearing_n) or 1.0
    ue, un = bearing_e / length, bearing_n / length
    side = 250.0
    far = offset_latlon(lat_b, lon_b, un * out_m, ue * out_m)
    near = offset_latlon(lat_a, lon_a, -un * out_m, -ue * out_m)
    return [
        offset_latlon(*near, -ue * side, un * side),
        offset_latlon(*far, -ue * side, un * side),
        offset_latlon(*far, ue * side, -un * side),
        offset_latlon(*near, ue * side, -un * side),
    ]


def _pad_patrol() -> list[tuple[float, float]]:
    """A short box around the two launch pads - the shakedown route."""
    clat = sum(p["lat"] for p in LAUNCH_PADS) / len(LAUNCH_PADS)
    clon = sum(p["lon"] for p in LAUNCH_PADS) / len(LAUNCH_PADS)
    r = 220.0
    return [
        offset_latlon(clat, clon, r, -r), offset_latlon(clat, clon, r, r),
        offset_latlon(clat, clon, -r, r), offset_latlon(clat, clon, -r, -r),
    ]


PATROL_ROUTES: dict[str, dict[str, Any]] = {
    "perimeter": {
        "name": "Operational area perimeter",
        "description": "The full boundary of the operational area, held inside the line.",
        "points": _inset_boundary(0.88),
    },
    "runways": {
        "name": "Runway sweep",
        "description": "Both runways end to end - the incursion and debris check.",
        "points": _runway_circuit(),
    },
    "terminal": {
        "name": "Terminal & apron circuit",
        "description": "Tight loop over the terminal, the stands and the parked aircraft.",
        "points": _apron_circuit(),
    },
    "approach": {
        "name": "Approach corridor",
        "description": "Out along the main runway centreline, covering both approaches.",
        "points": _approach_corridor(),
    },
    "pads": {
        "name": "Launch pad circuit",
        "description": "A short box around HP-1 and HP-2 - the post-maintenance shakedown.",
        "points": _pad_patrol(),
    },
}
DEFAULT_ROUTE = "perimeter"


# ── the inventory ────────────────────────────────────────
# Server-side filtering for the console's Inventory tab.

# Internal fields stripped from responses.
_INTERNAL_FIELDS = {"_bbox"}

# Scenery kinds, hidden from the inventory unless requested.
SCENERY_TYPES = {"tree", "agricultural_field", "solar_panel_table"}

TYPES: list[dict[str, Any]] = sorted(
    (
        {
            "type": t,
            "count": c,
            "scenery": t in SCENERY_TYPES,
            "max_height_m": max(
                (o["height_m"] for o in OBJECTS if o["type"] == t), default=0.0
            ),
        }
        for t, c in _DATA["counts"].items()
    ),
    key=lambda d: (d["scenery"], -d["count"]),
)


def public_object(o: dict[str, Any]) -> dict[str, Any]:
    """An object as the API serves it, with the grid reference added."""
    out = {k: v for k, v in o.items() if k not in _INTERNAL_FIELDS}
    out["grid_ref"] = grid_ref(o["lat"], o["lon"])
    return out


def _searchable(o: dict[str, Any]) -> str:
    cached = o.get("_search")
    if cached is None:
        parts = [str(o.get(k, "")) for k in
                 ("id", "type", "use", "designator", "species", "model", "stand",
                  "road_class", "surface", "crop", "name", "note", "category")]
        cached = " ".join(parts).lower()
        o["_search"] = cached
    return cached


def query_objects(
    q: str | None = None,
    types: list[str] | None = None,
    min_height: float | None = None,
    max_height: float | None = None,
    bounds: tuple[float, float, float, float] | None = None,
    near: tuple[float, float] | None = None,
    radius_m: float = 100.0,
    inside_area: bool | None = None,
    include_scenery: bool = True,
    sort: str = "type",
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    """Filter the dataset; returns a page of results plus the total matched.

    `near` (lat, lon) with `radius_m` selects objects by distance to their footprint.
    """
    needle = (q or "").strip().lower()
    wanted = set(types) if types else None

    def keep(o: dict[str, Any]) -> bool:
        if wanted is not None and o["type"] not in wanted:
            return False
        if not include_scenery and o["type"] in SCENERY_TYPES:
            return False
        if min_height is not None and o["height_m"] < min_height:
            return False
        if max_height is not None and o["height_m"] > max_height:
            return False
        if bounds is not None:
            s, w, n, e = bounds
            os_, ow, on, oe = bbox(o)
            if on < s or os_ > n or oe < w or ow > e:
                return False
        if inside_area is not None and inside_boundary(o["lat"], o["lon"]) != inside_area:
            return False
        if needle and needle not in _searchable(o):
            return False
        return True

    matched = [o for o in OBJECTS if keep(o)]

    # Proximity is measured to the footprint, not the centre.
    distances: dict[str, float] = {}
    if near is not None:
        lat, lon = near
        within = []
        for o in matched:
            d = 0.0 if contains(o, lat, lon) else _distance_to_footprint_m(o, lat, lon)
            if d <= radius_m:
                distances[o["id"]] = d
                within.append(o)
        matched = within

    if near is not None and sort in ("type", "distance"):
        matched.sort(key=lambda o: (distances.get(o["id"], 0.0), -o["height_m"]))
    elif sort == "height":
        matched.sort(key=lambda o: -o["height_m"])
    elif sort == "size":
        matched.sort(key=lambda o: -(o["length_m"] * o["width_m"]))
    elif sort == "id":
        matched.sort(key=lambda o: o["id"])
    else:
        matched.sort(key=lambda o: (o["type"], o["id"]))

    page = matched[offset: offset + limit]
    out = []
    for o in page:
        row = public_object(o)
        if o["id"] in distances:
            row["distance_m"] = round(distances[o["id"]], 1)
        out.append(row)
    return {
        "total": len(matched),
        "offset": offset,
        "limit": limit,
        "objects": out,
    }


@lru_cache(maxsize=1)
def _object_index() -> dict[str, dict[str, Any]]:
    return {o["id"]: o for o in OBJECTS}


def object_by_id(obj_id: str) -> dict[str, Any] | None:
    o = _object_index().get(obj_id)
    return public_object(o) if o else None


# ── climbing out ─────────────────────────────────────────

def _pad_clearance() -> float:
    """Height (m) below which objects sharing a pad are not obstacles.

    The tallest non-helipad object on any pad (e.g. the helicopter on HP-1)
    plus a 2 m margin.
    """
    tallest = 0.0
    for p in LAUNCH_PADS:
        for o in objects_at(p["lat"], p["lon"]):
            if o["type"] in NON_COLLIDABLE_TYPES or o["type"] == "helipad":
                continue
            tallest = max(tallest, o["height_m"])
    return round(tallest + 2.0, 1)


PAD_CLEARANCE_M: float = _pad_clearance()


def on_a_pad(lat: float, lon: float, alt_m: float) -> bool:
    """True while the drone is on or just above a launch pad (exempt from collision checks)."""
    if alt_m > PAD_CLEARANCE_M:
        return False
    return in_launch_area(lat, lon) is not None


def describe() -> dict[str, Any]:
    """The site definition the console draws; excludes the objects themselves."""
    return {
        "image": IMAGE_PATH,
        "name": SITE_NAME,
        "dataset_title": DATASET_TITLE,
        "image_size_px": [IMAGE_W_PX, IMAGE_H_PX],
        "meters_per_pixel": M_PER_PX,
        "map_width_m": MAP_WIDTH_M,
        "map_height_m": MAP_HEIGHT_M,
        "bounds": {
            "south": SOUTH_LAT, "west": WEST_LON,
            "north": NORTH_LAT, "east": EAST_LON,
        },
        "boundary": [list(p) for p in BOUNDARY],
        "boundary_area_km2": BOUNDARY_AREA_KM2,
        "grid": {
            "cell_size_m": _GRID_CELL_M,
            "columns": _GRID_COLS,
            "rows": _GRID_ROWS,
        },
        "launch_pads": [
            {
                "id": p["id"],
                "designator": p.get("designator"),
                "lat": p["lat"],
                "lon": p["lon"],
                "diameter_m": p.get("diameter_m", p["length_m"]),
                "grid_ref": grid_ref(p["lat"], p["lon"]),
            }
            for p in LAUNCH_PADS
        ],
        "default_pad": DEFAULT_PAD,
        "pad_radius_m": PAD_RADIUS_M,
        "pad_clearance_m": PAD_CLEARANCE_M,
        "home_lat": HOME_LAT,
        "home_lon": HOME_LON,
        "default_route": DEFAULT_ROUTE,
        "routes": {
            key: {
                "name": r["name"],
                "description": r["description"],
                "points": [list(p) for p in r["points"]],
            }
            for key, r in PATROL_ROUTES.items()
        },
        "object_types": TYPES,
        "total_objects": len(OBJECTS),
        "scenery_types": sorted(SCENERY_TYPES),
    }
