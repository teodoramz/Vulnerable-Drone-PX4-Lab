from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.config import settings
from app.registry import default_drones

IS_PX4 = settings.drone_backend == "px4"

if IS_PX4:
    from app.px4.agent import Px4Agent

    backend = Px4Agent(
        default_drones(settings.drone_count, settings.home_lat, settings.home_lon, settings.home_alt),
        c2_host=settings.c2_host,
        base_port=settings.px4_mavlink_base_port,
    )
else:
    from app.mavlink.transport import MavlinkTransport
    from app.mock.simulator import MockSimulator, SimDrone

    backend = MockSimulator([
        SimDrone(**d)
        for d in default_drones(settings.drone_count, settings.home_lat, settings.home_lon, settings.home_alt)
    ])
    mavlink_transport = MavlinkTransport(backend)

PHYSICS_DT = 0.05  # 20 Hz


@asynccontextmanager
async def lifespan(app: FastAPI):
    task: asyncio.Task | None = None
    if not IS_PX4:
        async def physics_loop() -> None:
            while True:
                backend.step(PHYSICS_DT)
                await asyncio.sleep(PHYSICS_DT)

        task = asyncio.create_task(physics_loop())
        # MAVLink 2 on UDP 14550 (app/mavlink/transport.py); shares `backend` with /ws.
        await mavlink_transport.start()
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
        if not IS_PX4:
            await mavlink_transport.stop()


app = FastAPI(title="Drone Simulator", version="1.0.0", lifespan=lifespan)


class PowerRequest(BaseModel):
    on: bool
    # Optional new home (launch pad); omitted leaves home unchanged.
    home_lat: float | None = None
    home_lon: float | None = None
    home_alt: float | None = None


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "backend": settings.drone_backend, "drones": len(backend.list_drones())}


@app.get("/drones")
async def list_drones() -> list[dict]:
    return backend.list_drones()


@app.post("/drones/{drone_id}/power")
async def power(drone_id: int, body: PowerRequest) -> dict:
    if body.home_lat is not None and body.home_lon is not None:
        relocated = await _maybe_await(
            backend.relocate(drone_id, body.home_lat, body.home_lon, body.home_alt)
        )
        if not relocated:
            raise HTTPException(status_code=404, detail="Unknown drone")
    ok = await _maybe_await(backend.power(drone_id, body.on))
    if not ok:
        raise HTTPException(status_code=404, detail="Unknown drone")
    return {"drone_id": drone_id, "on": body.on}


@app.post("/drones/{drone_id}/reset")
async def reset(drone_id: int) -> dict:
    """Reset the drone and its MAVLink surface (params, mission upload, telemetry peers).

    DELIBERATE VULNERABILITY: unauthenticated, like /power (see docs/SECURITY.md).
    """
    drones = backend.list_drones()
    if not any(d["id"] == drone_id for d in drones):
        raise HTTPException(status_code=404, detail="Unknown drone")

    cleared: dict = {}
    if not IS_PX4:
        cleared = mavlink_transport.reset_drone(drone_id)
        # Power-off runs the normal reset_to_home path.
        backend.power(drone_id, False)
    else:
        await _maybe_await(backend.power(drone_id, False))

    return {"drone_id": drone_id, "reset": True, "cleared": cleared}


async def _maybe_await(value):
    if asyncio.iscoroutine(value):
        return await value
    return value


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    """Mock flight transport: subscribe to one drone's telemetry and send verbs (mock backend only)."""
    await websocket.accept()
    subscription: dict[str, int | None] = {"id": None}

    async def sender() -> None:
        while True:
            drone_id = subscription["id"]
            if drone_id is not None and hasattr(backend, "telemetry"):
                sample = backend.telemetry(drone_id)
                if sample is not None:
                    await websocket.send_text(json.dumps({"type": "telemetry", **sample}))
            await asyncio.sleep(PHYSICS_DT)

    send_task = asyncio.create_task(sender())
    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            if "subscribe" in msg:
                subscription["id"] = int(msg["subscribe"])
            elif "verb" in msg and hasattr(backend, "apply_verb"):
                backend.apply_verb(int(msg["drone_id"]), msg["verb"], msg.get("args", {}))
    except (WebSocketDisconnect, json.JSONDecodeError, KeyError):
        pass
    finally:
        send_task.cancel()
