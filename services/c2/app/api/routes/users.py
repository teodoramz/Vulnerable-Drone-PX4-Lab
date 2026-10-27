from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.rbac import Permission, Role
from app.core.security import hash_password
from app.db.base import get_session
from app.models.user import User
from app.schemas.auth import UserOut
from app.schemas.user import UserCreate, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])
_admin = require_permission(Permission.USER_MANAGE)


async def _count_active_admins(session: AsyncSession) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(User)
            .where(User.role == Role.admin, User.is_active.is_(True))
        )
    ).scalar_one()


@router.get("", response_model=list[UserOut])
async def list_users(_: User = Depends(_admin), session: AsyncSession = Depends(get_session)):
    users = (await session.execute(select(User).order_by(User.id))).scalars().all()
    return [UserOut.model_validate(u) for u in users]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate, _: User = Depends(_admin), session: AsyncSession = Depends(get_session)
):
    exists = (
        await session.execute(select(User).where(User.username == body.username))
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")
    user = User(
        username=body.username,
        hashed_password=hash_password(body.password),
        role=body.role,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return UserOut.model_validate(user)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UserUpdate,
    admin: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
):
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    # Guard against demoting/deactivating the last admin (incl. yourself).
    demoting = (body.role is not None and body.role != Role.admin) or (body.is_active is False)
    if user.role == Role.admin and demoting and await _count_active_admins(session) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot remove the last active admin")

    if body.password is not None:
        user.hashed_password = hash_password(body.password)
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    await session.commit()
    await session.refresh(user)
    return UserOut.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int, admin: User = Depends(_admin), session: AsyncSession = Depends(get_session)
):
    if user_id == admin.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "You cannot delete your own account")
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.role == Role.admin and await _count_active_admins(session) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot delete the last active admin")
    await session.delete(user)
    await session.commit()
