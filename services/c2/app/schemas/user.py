from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.rbac import Role


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=4, max_length=128)
    role: Role = Role.observer


class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=4, max_length=128)
    role: Role | None = None
    is_active: bool | None = None
