from __future__ import annotations

import math

METERS_PER_DEG_LAT = 111320.0


def lon_offset_for_meters(lat: float, meters: float) -> float:
    """Longitude delta (degrees) for an east/west offset in meters at ``lat``."""
    return meters / (METERS_PER_DEG_LAT * math.cos(math.radians(lat)))


def swarm_lateral_offset(drone_id: int, spacing: float = 3.0) -> float:
    """Per-drone anti-collision lateral offset (meters), alternating E/W.

    Preserves the original lab's behavior (drone 0 = 0, drone 1 = +3m,
    drone 2 = -3m) and extends it for larger fleets.
    """
    if drone_id <= 0:
        return 0.0
    step = ((drone_id + 1) // 2) * spacing
    return step if drone_id % 2 == 1 else -step


def apply_swarm_offset(drone_id: int, lat: float, lon: float, spacing: float = 3.0) -> tuple[float, float]:
    offset = swarm_lateral_offset(drone_id, spacing)
    if offset == 0.0 or lat == 0.0:
        return lat, lon
    return lat, lon + lon_offset_for_meters(lat, offset)


def horizontal_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate planar distance (m) - fine over the short ranges in the lab."""
    lat_dist = (lat1 - lat2) * METERS_PER_DEG_LAT
    lon_dist = (lon1 - lon2) * METERS_PER_DEG_LAT * math.cos(math.radians(lat1))
    return math.hypot(lat_dist, lon_dist)
