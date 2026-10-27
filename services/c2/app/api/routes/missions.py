from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.rbac import Permission
from app.db.base import get_session
from app.models.mission import Mission, Waypoint
from app.models.user import User
from app.schemas.mission import MissionCreate, MissionOut

router = APIRouter(prefix="/api/missions", tags=["missions"])


@router.get("", response_model=list[MissionOut])
async def list_missions(
    _: User = Depends(require_permission(Permission.MISSION_READ)),
    session: AsyncSession = Depends(get_session),
):
    missions = (
        await session.execute(select(Mission).order_by(Mission.created_at.desc()))
    ).scalars().all()
    return [MissionOut.model_validate(m) for m in missions]


@router.post("", response_model=MissionOut, status_code=status.HTTP_201_CREATED)
async def create_mission(
    body: MissionCreate,
    user: User = Depends(require_permission(Permission.MISSION_WRITE)),
    session: AsyncSession = Depends(get_session),
):
    mission = Mission(
        name=body.name,
        created_by=user.id,
        created_by_name=user.username,
        created_at=datetime.now(timezone.utc),
        waypoints=[Waypoint(seq=w.seq, lat=w.lat, lon=w.lon, alt=w.alt) for w in body.waypoints],
    )
    session.add(mission)
    await session.commit()
    await session.refresh(mission)
    return MissionOut.model_validate(mission)


@router.get("/{mission_id}", response_model=MissionOut)
async def get_mission(
    mission_id: int,
    _: User = Depends(require_permission(Permission.MISSION_READ)),
    session: AsyncSession = Depends(get_session),
):
    mission = (
        await session.execute(select(Mission).where(Mission.id == mission_id))
    ).scalar_one_or_none()
    if mission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mission not found")
    return MissionOut.model_validate(mission)
