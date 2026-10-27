from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Permission, has_permission
from app.core.security import decode_token
from app.db.base import get_session
from app.models.user import User

_bearer = HTTPBearer(auto_error=True)


async def _load_user(payload: dict, session: AsyncSession) -> User | None:
    user = (
        await session.execute(select(User).where(User.id == payload.get("uid")))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return user


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    try:
        payload = decode_token(creds.credentials)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc
    user = await _load_user(payload, session)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


def require_permission(permission: Permission):
    """Dependency factory enforcing a single permission for the current user."""

    async def dependency(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user.role, permission):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Requires permission '{permission.value}'"
            )
        return user

    return dependency


async def authenticate_token(token: str, session: AsyncSession) -> User | None:
    """Token auth for the WebSocket handshake (no HTTP header available)."""
    try:
        payload = decode_token(token)
    except Exception:  # noqa: BLE001
        return None
    return await _load_user(payload, session)
