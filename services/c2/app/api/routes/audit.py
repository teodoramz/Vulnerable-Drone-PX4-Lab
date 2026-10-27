from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.rbac import Permission
from app.db.base import get_session
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.audit import AuditOut

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditOut])
async def list_audit(
    _: User = Depends(require_permission(Permission.AUDIT_READ)),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=200, le=1000),
    offset: int = Query(default=0, ge=0),
    drone_id: int | None = Query(default=None),
):
    stmt = select(AuditLog).order_by(AuditLog.id.desc())
    if drone_id is not None:
        stmt = stmt.where(AuditLog.drone_id == drone_id)
    rows = (await session.execute(stmt.limit(limit).offset(offset))).scalars().all()
    return [AuditOut.model_validate(r) for r in rows]
