from __future__ import annotations

import math
from dataclasses import dataclass, field

METERS_PER_DEG_LAT = 111320.0
MAX_GOTO_SPEED = 8.0     # m/s horizontal
MAX_GOTO_CLIMB = 3.0     # m/s vertical
LAND_SPEED = 1.0         # m/s controlled descent
CRASH_DESCENT_SPEED = 9.8  # m/s, uncontrolled fall after an in-air forced disarm
ARRIVAL_RADIUS_M = 2.0   # m, counts as "at" a waypoint/home


@dataclass
class SimDrone:
    id: int
    callsign: str
    home_lat: float
    home_lon: float
    home_alt: float

    enabled: bool = False
    armed: bool = False
    in_air: bool = False
    lat: float = 0.0
    lon: float = 0.0
    rel_alt: float = 0.0
    heading: float = 0.0

    # IDLE | VELOCITY | GOTO | LAND | RTL | MISSION | FALLING (the last three are MAVLink-only)
    mode: str = "IDLE"
    vN: float = 0.0
    vE: float = 0.0
    vD: float = 0.0
    target_lat: float = 0.0
    target_lon: float = 0.0
    target_rel_alt: float = 0.0

    # Mission uploaded over MAVLink: (lat, lon, rel_alt) tuples.
    mission_items: list[tuple[float, float, float]] = field(default_factory=list)
    mission_index: int = 0

    @property
    def abs_alt(self) -> float:
        return self.home_alt + self.rel_alt

    def reset_to_home(self) -> None:
        self.armed = False
        self.in_air = False
        self.lat = self.home_lat
        self.lon = self.home_lon
        self.rel_alt = 0.0
        self.heading = 0.0
        self.mode = "IDLE"
        self.vN = self.vE = self.vD = 0.0
        self.mission_items = []
        self.mission_index = 0


class MockSimulator:
    """Kinematic multi-drone simulator exposing the same low-level verbs as PX4."""

    def __init__(self, drones: list[SimDrone]):
        self.drones: dict[int, SimDrone] = {d.id: d for d in drones}

    # ── lifecycle API ────────────────────────────────────
    def list_drones(self) -> list[dict]:
        return [
            {
                "id": d.id,
                "callsign": d.callsign,
                "enabled": d.enabled,
                "lat": d.lat,
                "lon": d.lon,
                "rel_alt": d.rel_alt,
                "armed": d.armed,
                "home_lat": d.home_lat,
                "home_lon": d.home_lon,
            }
            for d in sorted(self.drones.values(), key=lambda x: x.id)
        ]

    def relocate(self, drone_id: int, lat: float, lon: float, alt: float | None = None) -> bool:
        """Move a drone's home; call before power(), which resets onto the new pad."""
        drone = self.drones.get(drone_id)
        if drone is None:
            return False
        drone.home_lat = lat
        drone.home_lon = lon
        if alt is not None:
            drone.home_alt = alt
        return True

    def power(self, drone_id: int, on: bool) -> bool:
        drone = self.drones.get(drone_id)
        if drone is None:
            return False
        drone.enabled = on
        drone.reset_to_home()
        return True

    # ── flight verbs ─────────────────────────────────────
    def apply_verb(self, drone_id: int, verb: str, args: dict) -> None:
        drone = self.drones.get(drone_id)
        if drone is None or not drone.enabled:
            return
        if verb == "arm":
            drone.armed = True
        elif verb == "set_velocity_ned":
            drone.mode = "VELOCITY"
            drone.vN = float(args.get("n", 0.0))
            drone.vE = float(args.get("e", 0.0))
            drone.vD = float(args.get("d", 0.0))
            drone.heading = float(args.get("yaw", drone.heading)) % 360
            if drone.vD < 0:
                drone.armed = True
        elif verb == "goto_location":
            drone.mode = "GOTO"
            drone.armed = True
            drone.target_lat = float(args["lat"])
            drone.target_lon = float(args["lon"])
            drone.target_rel_alt = float(args["abs_alt"]) - drone.home_alt
        elif verb == "land":
            drone.mode = "LAND"
        elif verb == "hold":
            drone.mode = "VELOCITY"
            drone.vN = drone.vE = drone.vD = 0.0

    # ── physics ──────────────────────────────────────────
    def step(self, dt: float) -> None:
        for drone in self.drones.values():
            if not drone.enabled:
                continue
            if drone.mode == "VELOCITY":
                self._move(drone, drone.vN, drone.vE, drone.vD, dt)
            elif drone.mode == "GOTO":
                self._step_goto(drone, dt)
            elif drone.mode == "LAND":
                self._move(drone, 0.0, 0.0, LAND_SPEED, dt)
                if drone.rel_alt <= 0.05:
                    drone.rel_alt = 0.0
                    drone.armed = False
                    drone.mode = "IDLE"
            elif drone.mode == "RTL":
                # Simplified RTL: straight home at the current altitude, then LAND.
                drone.target_lat = drone.home_lat
                drone.target_lon = drone.home_lon
                self._step_goto(drone, dt)
                if self._horizontal_distance(drone, drone.home_lat, drone.home_lon) <= ARRIVAL_RADIUS_M:
                    drone.mode = "LAND"
            elif drone.mode == "MISSION":
                if drone.mission_index < len(drone.mission_items):
                    lat, lon, alt = drone.mission_items[drone.mission_index]
                    drone.target_lat, drone.target_lon, drone.target_rel_alt = lat, lon, alt
                    self._step_goto(drone, dt)
                    at_pos = self._horizontal_distance(drone, lat, lon) <= ARRIVAL_RADIUS_M
                    at_alt = abs(drone.rel_alt - alt) <= 0.5
                    if at_pos and at_alt:
                        drone.mission_index += 1
                else:
                    drone.mode = "IDLE"  # mission complete -- hold position
            elif drone.mode == "FALLING":
                # Forced disarm (param2=21196) while airborne: it drops.
                self._move(drone, 0.0, 0.0, CRASH_DESCENT_SPEED, dt)
                if drone.rel_alt <= 0.0:
                    drone.rel_alt = 0.0
                    drone.mode = "IDLE"
            drone.rel_alt = max(0.0, drone.rel_alt)
            drone.in_air = drone.rel_alt > 0.3

    def _move(self, drone: SimDrone, vN: float, vE: float, vD: float, dt: float) -> None:
        # Record applied velocity every tick for GLOBAL_POSITION_INT.
        drone.vN, drone.vE, drone.vD = vN, vE, vD
        drone.lat += (vN * dt) / METERS_PER_DEG_LAT
        drone.lon += (vE * dt) / (METERS_PER_DEG_LAT * math.cos(math.radians(drone.lat)))
        drone.rel_alt += -vD * dt

    def _step_goto(self, drone: SimDrone, dt: float) -> None:
        north = (drone.target_lat - drone.lat) * METERS_PER_DEG_LAT
        east = (drone.target_lon - drone.lon) * METERS_PER_DEG_LAT * math.cos(math.radians(drone.lat))
        dist = math.hypot(north, east)
        if dist > 0.01:
            speed = min(MAX_GOTO_SPEED, dist / dt)
            vN = north / dist * speed
            vE = east / dist * speed
            drone.heading = math.degrees(math.atan2(east, north)) % 360
        else:
            vN = vE = 0.0
        climb = max(-MAX_GOTO_CLIMB, min(MAX_GOTO_CLIMB, (drone.target_rel_alt - drone.rel_alt) / dt))
        self._move(drone, vN, vE, -climb, dt)

    def _horizontal_distance(self, drone: SimDrone, lat: float, lon: float) -> float:
        north = (lat - drone.lat) * METERS_PER_DEG_LAT
        east = (lon - drone.lon) * METERS_PER_DEG_LAT * math.cos(math.radians(drone.lat))
        return math.hypot(north, east)

    def telemetry(self, drone_id: int) -> dict | None:
        drone = self.drones.get(drone_id)
        if drone is None:
            return None
        return {
            "drone_id": drone.id,
            "lat": drone.lat,
            "lon": drone.lon,
            "rel_alt": drone.rel_alt,
            "abs_alt": drone.abs_alt,
            "heading": drone.heading,
            "armed": drone.armed,
            "in_air": drone.in_air,
        }
