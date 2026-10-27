from __future__ import annotations

import abc
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field


@dataclass
class DroneRuntime:
    """Live state for one drone; the link updates telemetry, the fleet loop reads it."""

    id: int
    callsign: str
    home_lat: float
    home_lon: float
    home_alt: float

    enabled: bool = False
    # OFFLINE / BOOTING / IDLE / TAKEOFF / HOVER / GOTO / LAND / MANUAL /
    # ERROR / SIGNAL_LOST
    state: str = "OFFLINE"
    req_state: str = "IDLE"

    # telemetry
    lat: float = 0.0
    lon: float = 0.0
    alt: float = 0.0          # relative altitude (m)
    abs_alt: float = 0.0      # absolute altitude (m AMSL)
    heading: float = 0.0
    yaw_angle: float = 0.0
    is_armed: bool = False
    in_air: bool = False

    # Aircraft lost; cleared only by maintenance reset. The cause and the object
    # struck stay internal: no endpoint serves them, so the defender has to infer
    # them from the last fix and the inventory.
    lost: bool = False
    loss_cause: str | None = None     # "collision" | "out_of_area" | "link_lost"
    loss_object_id: str | None = None  # the object struck, if any
    # Where and when contact was lost.
    last_known_lat: float | None = None
    last_known_lon: float | None = None
    last_known_alt: float | None = None
    last_contact: str | None = None   # ISO-8601
    # time.monotonic() of the last position frame; 0.0 means none yet.
    telemetry_at: float = 0.0
    # When the current airframe entered service (ISO-8601), for the status API.
    alive_since: str | None = None
    # Ground speed (m/s), derived by the fleet engine.
    ground_speed: float = 0.0
    # Consecutive ticks outside the operational area (debounce).
    outside_ticks: int = 0
    # Consecutive ticks inside an obstacle's footprint (debounce).
    inside_ticks: int = 0

    # navigation targets
    target_lat: float = 0.0
    target_lon: float = 0.0
    target_alt: float = 10.0

    # patrol: looping (lat, lon) waypoints; patrol_index is the current leg
    patrol_points: list[tuple[float, float]] = field(default_factory=list)
    patrol_index: int = 0

    # manual velocity setpoints
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    yaw: float = 0.0


LogFn = Callable[[str], Awaitable[None]]


class DroneLink(abc.ABC):
    """A single drone's flight interface (MockLink or MavsdkLink)."""

    def __init__(self, runtime: DroneRuntime, log: LogFn):
        self.rt = runtime
        self.log = log

    def describe(self) -> str:
        """Human-readable endpoint, for error messages."""
        return type(self).__name__

    @abc.abstractmethod
    async def connect(self) -> bool:
        """Connect and begin streaming telemetry into ``self.rt``."""

    @abc.abstractmethod
    async def disconnect(self) -> None: ...

    @abc.abstractmethod
    async def arm(self) -> None: ...

    @abc.abstractmethod
    async def set_velocity_ned(self, north: float, east: float, down: float, yaw_deg: float) -> None:
        """Velocity setpoint in the NED frame (also engages offboard if needed)."""

    @abc.abstractmethod
    async def goto_location(self, lat: float, lon: float, abs_alt: float, yaw_deg: float) -> None: ...

    @abc.abstractmethod
    async def land(self) -> None: ...

    @abc.abstractmethod
    async def hold(self) -> None: ...
