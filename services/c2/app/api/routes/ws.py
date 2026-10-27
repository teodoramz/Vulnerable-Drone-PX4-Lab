from __future__ import annotations

import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.api.deps import authenticate_token
from app.core.rbac import Permission, has_permission
from app.db.base import AsyncSessionLocal
from app.models.user import User
from app.services.fleet import fleet
from app.services.ids import ids_service

router = APIRouter(tags=["ws"])

# Velocity-stream axes, kept out of the audit log.
_STREAM_AXES = {"vx", "vy", "vz", "yaw"}


async def _handle_command(ws: WebSocket, user: User, data: dict) -> None:
    drone_id = data.get("drone_id")
    command = data.get("command")
    if drone_id is None or command is None:
        return

    if not has_permission(user.role, Permission.DRONE_COMMAND):
        await ws.send_text(json.dumps({"type": "error", "msg": "Observers cannot command drones."}))
        return

    if not fleet.can_command(drone_id, user):
        await ws.send_text(json.dumps({
            "type": "error", "drone_id": drone_id,
            "msg": f"Drone {drone_id} is not under your control. Claim it first.",
        }))
        await fleet.audit(user, drone_id, command, {"reason": "no_claim"}, result="denied")
        return

    params = {k: v for k, v in data.items() if k not in ("drone_id", "command")}
    if command == "MANUAL" and data.get("stream") and _STREAM_AXES & params.keys():
        params["_stream"] = True

    ok, msg = await fleet.apply_command(drone_id, command, params, user)
    if not ok:
        await ws.send_text(json.dumps({"type": "error", "drone_id": drone_id, "msg": msg}))


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket, token: str = Query(...)) -> None:
    async with AsyncSessionLocal() as session:
        user = await authenticate_token(token, session)
    if user is None:
        await ws.close(code=4401)
        return

    await ws.accept()
    fleet.manager.connect(ws, user)
    try:
        # Prime the client with log history, telemetry and recent IDS alerts.
        for entry in list(fleet.logs):
            await ws.send_text(json.dumps(entry))
        await ws.send_text(fleet._telemetry_payload())
        for alert in ids_service.recent(limit=ids_service.alerts.maxlen or 500):
            await ws.send_text(json.dumps({"type": "ids_alert", "alert": alert}))

        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            await _handle_command(ws, user, data)
    except WebSocketDisconnect:
        pass
    finally:
        fleet.manager.disconnect(ws)
