from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("sensor.hub")


class WebSocketHub:
    """Tracks connected /ws clients and fans out alert/flow events to all
    of them, dropping any connection that errors on send."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    def connect(self, ws: WebSocket) -> None:
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)

    @property
    def count(self) -> int:
        return len(self._connections)

    async def broadcast(self, message: dict[str, Any]) -> None:
        if not self._connections:
            return
        text = json.dumps(message)
        dead = []
        for ws in list(self._connections):
            try:
                await ws.send_text(text)
            except Exception as exc:  # noqa: BLE001 - a dead socket must not stop the fan-out
                logger.debug("hub: dropping dead connection: %s", exc)
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)
