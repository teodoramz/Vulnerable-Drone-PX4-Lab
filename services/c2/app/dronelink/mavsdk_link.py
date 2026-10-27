from __future__ import annotations

import asyncio
import contextlib
import math
import time
from collections.abc import Awaitable, Callable

from app.dronelink.base import DroneLink, DroneRuntime, LogFn

_M_PER_DEG_LAT = 111320.0

# Params that let headless PX4 SITL arm and fly without RC or preflight.
# No EKF2_* here: writing one restarts the estimator and re-origins the local frame.
PX4_PARAMS = {
    "COM_RC_IN_MODE": 1,
    "NAV_RCL_ACT": 0,
    "NAV_DLL_ACT": 0,
    "COM_RCL_EXCEPT": 4,
    "COM_ARM_SW_ARM_EN": 1,
    "CBRK_SUPPLY_CHK": 894281,
    "CBRK_IO_SAFETY": 22027,
}

FAILURE_KEYWORDS = ("CRITICAL", "EMERGENCY", "MAG", "Attitude")


class MavsdkLink(DroneLink):
    """Adapter to PX4 over MAVLink via MAVSDK; hides the offboard quirks."""

    def __init__(
        self,
        runtime: DroneRuntime,
        log: LogFn,
        system_address: str,
        grpc_port: int,
        on_failure: Callable[[int], Awaitable[None]] | None = None,
    ):
        super().__init__(runtime, log)
        self.system_address = system_address
        self.grpc_port = grpc_port
        self.on_failure = on_failure
        self.system = None
        self._offboard_active = False
        self._tasks: list[asyncio.Task] = []

    def describe(self) -> str:
        return f"PX4 MAVLink link ({self.system_address}, mavsdk_server grpc {self.grpc_port})"

    async def connect(self) -> bool:
        from mavsdk import System  # lazy: px4 mode only

        await self.log(
            f"{self.rt.callsign}: connecting to PX4…",
            level="cmd", drone_id=self.rt.id,
            detail=f"{self.system_address} (mavsdk_server grpc {self.grpc_port})",
        )
        self.system = System(port=self.grpc_port)
        await self.system.connect(system_address=self.system_address)

        connected = False
        async for state in self.system.core.connection_state():
            if state.is_connected:
                connected = True
                break
        if not connected:
            return False

        await self.log(f"{self.rt.callsign} connected to the PX4 autopilot.", drone_id=self.rt.id)
        self._tasks.append(asyncio.create_task(self._telemetry_loop()))
        self._tasks.append(asyncio.create_task(self._status_loop()))

        for param, value in PX4_PARAMS.items():
            with contextlib.suppress(Exception):
                await self.system.param.set_param_int(param, value)

        # Wait for full armability; position health goes true before preflight ends.
        with contextlib.suppress(asyncio.TimeoutError, Exception):
            await asyncio.wait_for(self._wait_ready(), timeout=90.0)
        return True

    async def _wait_ready(self) -> None:
        """Block until every preflight check passes (i.e. the drone will arm)."""
        async for ok in self.system.telemetry.health_all_ok():
            if ok:
                return

    def _ned_to_latlon(self, north_m: float, east_m: float) -> tuple[float, float]:
        """Local NED offset (metres from spawn) → geo position, anchored at home."""
        lat = self.rt.home_lat + north_m / _M_PER_DEG_LAT
        lon = self.rt.home_lon + east_m / (_M_PER_DEG_LAT * math.cos(math.radians(self.rt.home_lat)))
        return lat, lon

    def _latlon_to_ned(self, lat: float, lon: float) -> tuple[float, float]:
        """Geo position → local NED offset (metres from spawn)."""
        north_m = (lat - self.rt.home_lat) * _M_PER_DEG_LAT
        east_m = (lon - self.rt.home_lon) * _M_PER_DEG_LAT * math.cos(math.radians(self.rt.home_lat))
        return north_m, east_m

    async def _telemetry_loop(self) -> None:
        # Use the home-anchored local NED frame, not GPS: PX4's SIH origin is unreliable.
        async def positions() -> None:
            async for pv in self.system.telemetry.position_velocity_ned():
                north, east, down = pv.position.north_m, pv.position.east_m, pv.position.down_m
                self.rt.lat, self.rt.lon = self._ned_to_latlon(north, east)
                self.rt.alt = -down
                self.rt.abs_alt = self.rt.home_alt + (-down)
                self.rt.telemetry_at = time.monotonic()

        async def headings() -> None:
            async for hdg in self.system.telemetry.heading():
                self.rt.heading = hdg.heading_deg

        async def armed() -> None:
            async for is_armed in self.system.telemetry.armed():
                self.rt.is_armed = is_armed

        async def in_air() -> None:
            async for flying in self.system.telemetry.in_air():
                self.rt.in_air = flying

        with contextlib.suppress(Exception):
            await asyncio.gather(positions(), headings(), armed(), in_air())

    async def _status_loop(self) -> None:
        with contextlib.suppress(Exception):
            async for status in self.system.telemetry.status_text():
                await self.log(f"PX4: {status.text}", level="warn", drone_id=self.rt.id)
                if any(k in status.text for k in FAILURE_KEYWORDS):
                    self.rt.state = "ERROR"
                    if self.on_failure is not None:
                        await self.on_failure(self.rt.id)
                    return

    async def disconnect(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        if self.system is not None and self._offboard_active:
            with contextlib.suppress(Exception):
                await self.system.offboard.stop()
        self.system = None
        self._offboard_active = False

    async def arm(self) -> None:
        # The first arm can be rejected briefly after health_all_ok; retry.
        from mavsdk.action import ActionError

        for attempt in range(12):
            if self.rt.is_armed:
                return
            try:
                await self.system.action.arm()
                return
            except ActionError as exc:
                if attempt == 0:
                    await self.log(
                        f"{self.rt.callsign}: arm rejected, retrying.",
                        level="warn", drone_id=self.rt.id,
                        detail=f"{type(exc).__name__}: {exc}",
                    )
                await asyncio.sleep(0.5)
            except Exception:  # noqa: BLE001
                await asyncio.sleep(0.5)

    async def _engage_offboard(self, setpoint, send) -> None:
        """Send a setpoint, then start offboard, retrying both together.

        PX4 refuses offboard.start() (NO_SETPOINT_SET) before a setpoint has
        been sent. Logs an error if offboard cannot be engaged.
        """
        from mavsdk.offboard import OffboardError

        last: Exception | None = None
        for attempt in range(4):
            try:
                await send(setpoint)
            except Exception as exc:  # noqa: BLE001 - reported below
                last = exc
                await asyncio.sleep(0.25)
                continue
            if self._offboard_active:
                return
            try:
                await self.system.offboard.start()
                self._offboard_active = True
                return
            except OffboardError as exc:
                # Typically NO_SETPOINT_SET; resend before starting again.
                last = exc
                await asyncio.sleep(0.25)

        self._offboard_active = False
        await self.log(
            f"{self.rt.callsign}: could not enter offboard control - "
            f"the aircraft will not respond to commands.",
            level="error", drone_id=self.rt.id,
            detail=f"{type(last).__name__}: {last}" if last else "unknown",
        )

    async def _ensure_offboard(self, setpoint) -> None:
        await self._engage_offboard(setpoint, self.system.offboard.set_velocity_ned)

    async def _ensure_offboard_position(self, setpoint) -> None:
        await self._engage_offboard(setpoint, self.system.offboard.set_position_ned)

    async def _stop_offboard(self) -> None:
        if self._offboard_active:
            with contextlib.suppress(Exception):
                await self.system.offboard.stop()
            self._offboard_active = False


    async def set_velocity_ned(self, north: float, east: float, down: float, yaw_deg: float) -> None:
        from mavsdk.offboard import VelocityNedYaw

        await self._ensure_offboard(VelocityNedYaw(north, east, down, yaw_deg))

    async def goto_location(self, lat: float, lon: float, abs_alt: float, yaw_deg: float) -> None:
        # Local NED frame; mavsdk_server keeps streaming the setpoint.
        from mavsdk.offboard import PositionNedYaw

        north, east = self._latlon_to_ned(lat, lon)
        down = -(abs_alt - self.rt.home_alt)
        await self._ensure_offboard_position(PositionNedYaw(north, east, down, yaw_deg))

    async def land(self) -> None:
        await self._stop_offboard()
        with contextlib.suppress(Exception):
            await self.system.action.land()

    async def hold(self) -> None:
        from mavsdk.offboard import VelocityNedYaw

        await self._ensure_offboard(VelocityNedYaw(0.0, 0.0, 0.0, self.rt.yaw_angle))
