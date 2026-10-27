from __future__ import annotations

from pydantic import BaseModel


class ClaimInfo(BaseModel):
    held: bool = False
    user_id: int | None = None
    username: str | None = None
    mine: bool = False


class DroneState(BaseModel):
    id: int
    callsign: str
    model: str
    enabled: bool
    state: str
    lat: float
    lon: float
    alt: float
    heading: float
    armed: bool
    home_lat: float
    home_lon: float
    # Contact lost; the cause is deliberately not exposed.
    lost: bool = False
    # Where contact was lost.
    last_known_lat: float | None = None
    last_known_lon: float | None = None
    last_known_alt: float | None = None
    last_contact: str | None = None
    # Ground speed in m/s.
    ground_speed: float = 0.0
    claim: ClaimInfo


class PowerRequest(BaseModel):
    on: bool
    # Launch pad designator (e.g. "HP-1"); default is the current pad.
    pad: str | None = None


class ResetRequest(BaseModel):
    """Maintenance reset. `pad` relocates the replacement airframe."""
    pad: str | None = None
