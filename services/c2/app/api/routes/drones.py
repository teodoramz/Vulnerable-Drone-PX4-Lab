from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permission
from app.core.rbac import Permission, Role
from app.db.base import get_session
from app.models.drone import Drone
from app.models.user import User
from app.schemas.drone import ClaimInfo, DroneState, PowerRequest, ResetRequest
from app.services import site
from app.services.fleet import fleet

router = APIRouter(prefix="/api/drones", tags=["drones"])


def _claim_info(drone_id: int, user: User) -> ClaimInfo:
    rec = fleet.get_claim(drone_id)
    if rec is None:
        return ClaimInfo(held=False)
    return ClaimInfo(held=True, user_id=rec.user_id, username=rec.username, mine=rec.user_id == user.id)


@router.get("/site", deprecated=True)
async def get_site(_: User = Depends(get_current_user)) -> dict:
    """Deprecated alias of `GET /api/site`."""
    return site.describe()


@router.get("", response_model=list[DroneState])
async def list_drones(
    user: User = Depends(require_permission(Permission.DRONE_READ)),
    session: AsyncSession = Depends(get_session),
):
    registry = {d.id: d for d in (await session.execute(select(Drone).order_by(Drone.id))).scalars()}
    out: list[DroneState] = []
    for drone_id, rt in sorted(fleet.runtimes.items()):
        reg = registry.get(drone_id)
        out.append(DroneState(
            id=drone_id,
            callsign=rt.callsign,
            model=reg.model if reg else "x500",
            enabled=rt.enabled,
            state=rt.state if rt.enabled else "OFFLINE",
            lat=rt.lat,
            lon=rt.lon,
            alt=rt.alt,
            heading=rt.heading,
            armed=rt.is_armed,
            home_lat=rt.home_lat,
            home_lon=rt.home_lon,
            lost=rt.lost,
            last_known_lat=rt.last_known_lat,
            last_known_lon=rt.last_known_lon,
            last_known_alt=rt.last_known_alt,
            last_contact=rt.last_contact,
            ground_speed=round(rt.ground_speed, 2),
            claim=_claim_info(drone_id, user),
        ))
    return out


def _require_drone(drone_id: int) -> None:
    if drone_id not in fleet.runtimes:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown drone")


@router.post("/{drone_id}/claim")
async def claim_drone(
    drone_id: int, user: User = Depends(require_permission(Permission.DRONE_CLAIM))
):
    _require_drone(drone_id)
    ok, holder = await fleet.acquire_claim(drone_id, user)
    if not ok:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Drone is already controlled by '{holder.username}'" if holder else "Drone is claimed",
        )
    return {"status": "claimed", "drone_id": drone_id}


@router.post("/{drone_id}/release")
async def release_drone(
    drone_id: int, user: User = Depends(require_permission(Permission.DRONE_CLAIM))
):
    _require_drone(drone_id)
    if not await fleet.release_claim(drone_id, user, force=False):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not hold this drone")
    return {"status": "released", "drone_id": drone_id}


@router.post("/{drone_id}/force-release")
async def force_release_drone(
    drone_id: int, user: User = Depends(require_permission(Permission.DRONE_FORCE_RELEASE))
):
    _require_drone(drone_id)
    await fleet.release_claim(drone_id, user, force=True)
    return {"status": "force-released", "drone_id": drone_id}


@router.post("/{drone_id}/reset")
async def reset_drone(
    drone_id: int,
    body: ResetRequest | None = None,
    user: User = Depends(require_permission(Permission.DRONE_POWER)),
):
    """Maintenance reset; same access rule as power-off (admin, or claim holder)."""
    _require_drone(drone_id)
    if not fleet.can_command(drone_id, user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "You do not control this drone - claim it first, or ask an admin to reset it.",
        )
    result = await fleet.maintenance_reset(drone_id, user, pad=body.pad if body else None)
    if not result.get("ok"):
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Reset failed: {result.get('error', 'the drone service did not respond')}",
        )
    return {"status": "reset", "drone_id": drone_id, "steps": result["steps"]}


@router.post("/{drone_id}/power")
async def power_drone(
    drone_id: int,
    body: PowerRequest,
    user: User = Depends(require_permission(Permission.DRONE_POWER)),
):
    _require_drone(drone_id)
    if body.on:
        # Powering on takes the claim.
        ok, holder = await fleet.acquire_claim(drone_id, user)
        if not ok:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Drone is controlled by '{holder.username}'" if holder else "Drone is claimed",
            )
        await fleet.power_on(drone_id, pad=body.pad)
        await fleet.audit(user, drone_id, "POWER_ON", {"pad": body.pad})
        return {"status": "powering-on", "drone_id": drone_id}

    # Powering off requires the claim (admins may override).
    if not fleet.can_command(drone_id, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not control this drone")
    await fleet.power_off(drone_id)
    await fleet.audit(user, drone_id, "POWER_OFF", {})
    return {"status": "powering-off", "drone_id": drone_id}
