"""The public drone status API - deliberately unauthenticated.

Example: GET /api/public/drone -> {"callsign": "Sentinel", "state": "alive", "since": "..."}

State is "alive" (in service, flying or not) or "missing" (contact lost, with
the last fix). The cause of a loss is never served. It returns to "alive"
only after a maintenance reset.

DELIBERATE LAB WEAKNESS: no authentication, so an attacker can see whether
their attempt worked.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.services.fleet import airborne, fleet

router = APIRouter(prefix="/api/public", tags=["public"])


def _status(drone_id: int) -> dict:
    rt = fleet.runtimes[drone_id]
    out: dict = {
        "drone_id": drone_id,
        "callsign": rt.callsign,
        "state": "missing" if rt.lost else "alive",
    }
    if rt.lost:
        out["last_known"] = {
            "lat": round(rt.last_known_lat, 6) if rt.last_known_lat is not None else None,
            "lon": round(rt.last_known_lon, 6) if rt.last_known_lon is not None else None,
            "alt_m": round(rt.last_known_alt, 1) if rt.last_known_alt is not None else None,
        }
        out["last_contact"] = rt.last_contact
    else:
        out["since"] = rt.alive_since
        out["flying"] = bool(rt.enabled and airborne(rt))
    return out


@router.get("/drone")
async def drone_status() -> dict:
    """Status of the scenario's drone. No authentication."""
    if not fleet.runtimes:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Fleet not started")
    return _status(min(fleet.runtimes))


@router.get("/drones")
async def fleet_status() -> dict:
    """Every drone, for when DRONE_COUNT is raised above one."""
    return {"drones": [_status(i) for i in sorted(fleet.runtimes)]}
