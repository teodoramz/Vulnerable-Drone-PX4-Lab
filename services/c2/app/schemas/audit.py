from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ts: datetime
    user_id: int | None
    username: str
    drone_id: int | None
    action: str
    params: dict
    result: str
