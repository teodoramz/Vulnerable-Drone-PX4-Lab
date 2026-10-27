from __future__ import annotations

import json
from collections import deque

from app.config import settings
from app.schemas.ids import IdsAlertIn
from app.services.fleet import fleet


class IdsService:
    """Bounded buffer of recent Suricata alerts pushed by the `sensor` service.

    DELIBERATE LAB WEAKNESS - do not "fix": alerts reach operators only via
    sensor -> POST /api/ids/alerts -> C2 -> WebSocket. An attacker who
    compromises the C2 can drop or tamper with alerts undetected; the sensor's
    own API on :9200/tcp is the out-of-band source of truth.
    """

    def __init__(self, cap: int | None = None) -> None:
        self.alerts: deque[dict] = deque(maxlen=cap or settings.ids_buffer_size)

    async def ingest(self, alert: IdsAlertIn) -> dict:
        payload = alert.model_dump()
        self.alerts.append(payload)
        # Deliberate weakness (see class docstring): the only path to operators.
        await fleet.manager.broadcast(json.dumps({"type": "ids_alert", "alert": payload}))
        return payload

    def recent(self, limit: int = 100, severity: int | None = None) -> list[dict]:
        items = list(self.alerts)
        if severity is not None:
            items = [a for a in items if a["severity"] == severity]
        return items[-limit:]


ids_service = IdsService()
