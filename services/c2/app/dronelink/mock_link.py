from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import Awaitable
from typing import Callable

import websockets

from app.dronelink.base import DroneLink, DroneRuntime, LogFn

# States in which a disarm is unexpected (LAND and IDLE disarm normally).
AIRBORNE_STATES = {"TAKEOFF", "HOVER", "GOTO", "PATROL", "MANUAL"}


class MockLink(DroneLink):
    """Adapter to the mock simulator over a per-drone WebSocket."""

    def __init__(
        self,
        runtime: DroneRuntime,
        log: LogFn,
        ws_url: str,
        on_failure: Callable[[int], Awaitable[None]] | None = None,
    ):
        super().__init__(runtime, log)
        self.ws_url = ws_url
        self.on_failure = on_failure
        self.ws: websockets.WebSocketClientProtocol | None = None
        self._reader: asyncio.Task | None = None

    def describe(self) -> str:
        return f"mock flight link (WebSocket {self.ws_url})"

    async def connect(self) -> bool:
        try:
            self.ws = await websockets.connect(self.ws_url, open_timeout=10)
        except Exception as exc:  # noqa: BLE001
            await self.log(
                f"{self.rt.callsign}: cannot reach the drone service.",
                level="error", drone_id=self.rt.id,
                detail=f"{self.ws_url} - {type(exc).__name__}: {exc}",
            )
            return False
        await self.ws.send(json.dumps({"hello": True, "subscribe": self.rt.id}))
        self._reader = asyncio.create_task(self._read_loop())
        return True

    async def _read_loop(self) -> None:
        assert self.ws is not None
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                if msg.get("type") == "telemetry" and msg.get("drone_id") == self.rt.id:
                    was_armed = self.rt.is_armed
                    self.rt.lat = msg["lat"]
                    self.rt.lon = msg["lon"]
                    self.rt.alt = msg["rel_alt"]
                    self.rt.telemetry_at = time.monotonic()
                    self.rt.abs_alt = msg["abs_alt"]
                    self.rt.heading = msg["heading"]
                    self.rt.is_armed = msg["armed"]
                    self.rt.in_air = msg["in_air"]

                    # External disarm (e.g. the MAVLink kill attack).
                    if was_armed and not self.rt.is_armed and self.rt.state in AIRBORNE_STATES:
                        await self.log(
                            f"Drone {self.rt.id} disarmed by external command "
                            f"while {self.rt.state} - it is falling."
                        )
                        self.rt.state = "ERROR"
                        if self.on_failure is not None:
                            await self.on_failure(self.rt.id)
                        return
        except Exception:  # noqa: BLE001
            pass

    async def _send(self, verb: str, **args) -> None:
        if self.ws is None:
            return
        with contextlib.suppress(Exception):
            await self.ws.send(json.dumps({"drone_id": self.rt.id, "verb": verb, "args": args}))

    async def disconnect(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
        if self.ws is not None:
            with contextlib.suppress(Exception):
                await self.ws.close()
        self.ws = None

    async def arm(self) -> None:
        await self._send("arm")

    async def set_velocity_ned(self, north: float, east: float, down: float, yaw_deg: float) -> None:
        await self._send("set_velocity_ned", n=north, e=east, d=down, yaw=yaw_deg)

    async def goto_location(self, lat: float, lon: float, abs_alt: float, yaw_deg: float) -> None:
        await self._send("goto_location", lat=lat, lon=lon, abs_alt=abs_alt, yaw=yaw_deg)

    async def land(self) -> None:
        await self._send("land")

    async def hold(self) -> None:
        await self._send("hold")
