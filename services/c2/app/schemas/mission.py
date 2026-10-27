from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WaypointIn(BaseModel):
    seq: int
    lat: float
    lon: float
    alt: float = 15.0


class MissionCreate(BaseModel):
    name: str
    waypoints: list[WaypointIn] = []


class WaypointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    lat: float
    lon: float
    alt: float


class MissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_by_name: str
    created_at: datetime
    waypoints: list[WaypointOut]
