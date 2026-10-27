from __future__ import annotations

import asyncio
import contextlib
import json
import random
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import settings
from app.core.rbac import Role
from app.db.base import AsyncSessionLocal
from app.dronelink.base import DroneLink, DroneRuntime
from app.dronelink.mock_link import MockLink
from app.models.audit import AuditLog
from app.models.drone import Drone
from app.models.telemetry import TelemetrySample
from app.models.user import User
from app.services import site, swarm
from app.services.drone_client import DroneClient

VELOCITY_MODES = {"TAKEOFF", "HOVER", "MANUAL"}
FLIGHT_COMMANDS = {"TAKEOFF", "GOTO", "LAND", "HOVER", "MANUAL", "CANCEL", "PATROL"}

# Distance (m) to a patrol waypoint at which the drone advances to the next.
PATROL_ARRIVE_M = 3.0
# Absolute altitude tolerance (m) for completing a takeoff.
TAKEOFF_TOLERANCE_M = 1.0

# Telemetry staleness (s) after which the aircraft is declared lost.
LINK_TIMEOUT_S = 8.0

# Consecutive control-loop ticks (10 Hz) before a breach/collision counts.
BOUNDARY_BREACH_TICKS = 5
COLLISION_TICKS = 3

# `attack` is kept distinct from `error` so forged commands stand out.
LOG_LEVELS = {"info", "cmd", "warn", "error", "attack"}

# States in which the aircraft is off the ground.
AIRBORNE_STATES = {"TAKEOFF", "HOVER", "GOTO", "PATROL", "LAND", "MANUAL"}
# Altitude (m) above which it is not sitting on a pad.
AIRBORNE_ALT_M = 1.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def airborne(rt: DroneRuntime) -> bool:
    """Whether the aircraft is off the ground.

    `in_air` comes from its own telemetry subscription, which can still read
    false seconds after the control loop reports a hover, so the C2's own
    state and altitude count as well.
    """
    return rt.in_air or (rt.state in AIRBORNE_STATES and rt.alt > AIRBORNE_ALT_M)


@dataclass
class ClaimRecord:
    user_id: int
    username: str
    acquired_at: datetime
    expires_at: datetime


class ConnectionManager:
    """Tracks authenticated WebSocket clients for telemetry/log fan-out."""

    def __init__(self) -> None:
        self.active: dict[object, User] = {}

    def connect(self, ws: object, user: User) -> None:
        self.active[ws] = user

    def disconnect(self, ws: object) -> None:
        self.active.pop(ws, None)

    def connected_user_ids(self) -> set[int]:
        return {u.id for u in self.active.values()}

    async def broadcast(self, payload: str) -> None:
        for ws in list(self.active):
            try:
                await ws.send_text(payload)
            except Exception:  # noqa: BLE001
                self.active.pop(ws, None)


class FleetService:
    """Owns live drone state, control loops, claims, audit writes and telemetry broadcast."""

    def __init__(self) -> None:
        self.runtimes: dict[int, DroneRuntime] = {}
        self.links: dict[int, DroneLink] = {}
        self.loops: dict[int, asyncio.Task] = {}
        self.claims: dict[int, ClaimRecord] = {}
        self.logs: deque[dict] = deque(maxlen=200)
        self.manager = ConnectionManager()
        self.drone = DroneClient(settings.drone_api_url)
        self._bg: list[asyncio.Task] = []
        # drone_id -> (lat, lon, unix_ts), for the speed derivation
        self._last_fix: dict[int, tuple[float, float, float]] = {}

    # ── lifecycle ────────────────────────────────────────
    async def startup(self) -> None:
        async with AsyncSessionLocal() as session:
            drones = (await session.execute(select(Drone).order_by(Drone.id))).scalars().all()
        for d in drones:
            self.runtimes[d.id] = DroneRuntime(
                id=d.id, callsign=d.callsign,
                home_lat=d.home_lat, home_lon=d.home_lon, home_alt=d.home_alt,
                alive_since=_now().isoformat(),
            )
        self._bg.append(asyncio.create_task(self._broadcast_loop()))
        self._bg.append(asyncio.create_task(self._claim_keeper_loop()))
        self._bg.append(asyncio.create_task(self._telemetry_persist_loop()))
        unit = "drone" if len(drones) == 1 else "drones"
        await self.log(f"C2 fleet engine online - {settings.drone_backend} backend, {len(drones)} {unit}.")
        if settings.auto_patrol:
            for d in drones:
                self._track(asyncio.create_task(self._auto_launch_patrol(d.id)))

    async def _auto_launch_patrol(self, drone_id: int) -> None:
        """Power on, climb and start the default patrol so the range comes up flying."""
        route = site.PATROL_ROUTES.get(settings.auto_patrol_route)
        if route is None and site.PATROL_ROUTES:
            route = next(iter(site.PATROL_ROUTES.values()))
        points = [(float(la), float(lo)) for la, lo in (route or {}).get("points", [])]
        if len(points) < 2:
            await self.log(
                f"Auto-patrol skipped: route '{settings.auto_patrol_route}' has too few points.",
                level="warn", drone_id=drone_id,
            )
            return

        try:
            await self.power_on(drone_id)
        except Exception as exc:  # noqa: BLE001
            await self.log("Auto-patrol: power-on failed.", level="error",
                           drone_id=drone_id, detail=f"{type(exc).__name__}: {exc}")
            return

        rt = self.runtimes.get(drone_id)
        if rt is None:
            return

        # Wait for the flight link; the connect budget is 120 s.
        for _ in range(1300):
            if not rt.enabled:
                return
            if rt.state == "IDLE":
                break
            await asyncio.sleep(0.1)
        else:
            return

        rt.target_alt = settings.auto_patrol_alt
        rt.patrol_points = points
        rt.patrol_index = 0
        rt.req_state = "TAKEOFF"

        # Wait for the control loop to flip TAKEOFF -> HOVER.
        airborne = False
        for _ in range(900):
            if not rt.enabled:
                return
            if rt.state == "HOVER":
                airborne = True
                break
            await asyncio.sleep(0.1)

        if not airborne:
            # Takeoff never completed (e.g. the vehicle would not arm).
            await self.log(
                f"{rt.callsign}: auto-patrol aborted - takeoff did not complete.",
                level="warn", drone_id=drone_id,
                detail="The vehicle did not reach patrol altitude; it remains on the pad.",
            )
            return

        rt.patrol_index = 0
        rt.req_state = "PATROL"
        await self.log(
            f"{rt.callsign}: auto-patrol engaged - route '{settings.auto_patrol_route}', "
            f"{len(points)} legs at {settings.auto_patrol_alt:.0f} m.",
            level="cmd", drone_id=drone_id,
        )

    async def shutdown(self) -> None:
        for task in list(self.loops.values()) + self._bg:
            task.cancel()
        for link in list(self.links.values()):
            with contextlib.suppress(Exception):
                await link.disconnect()
        await self.drone.aclose()

    async def log(
        self,
        msg: str,
        level: str = "info",
        drone_id: int | None = None,
        detail: str | None = None,
    ) -> None:
        """Record and broadcast an operator-facing log line.

        `level` is one of LOG_LEVELS; `detail` carries the specifics of a failure.
        """
        entry = {
            "type": "log",
            "level": level if level in LOG_LEVELS else "info",
            "ts": _now().isoformat(),
            "msg": msg,
            "drone_id": drone_id,
        }
        if detail:
            entry["detail"] = detail

        self.logs.append(entry)
        line = f"[{entry['level'].upper():<6}] {msg}" + (f"  ({detail})" if detail else "")
        try:
            print(line, flush=True)
        except UnicodeEncodeError:
            # Console may not be UTF-8.
            print(line.encode("ascii", "replace").decode(), flush=True)
        await self.manager.broadcast(json.dumps(entry))

    def _track(self, task: asyncio.Task) -> None:
        """Keep a reference to a detached task so it is not garbage-collected."""
        self._bg.append(task)
        task.add_done_callback(lambda t: self._bg.remove(t) if t in self._bg else None)

    # ── power on/off ─────────────────────────────────────
    async def power_on(self, drone_id: int, pad: str | None = None) -> None:
        """Power a drone on at `pad` (a site designator); default is its current pad."""
        rt = self.runtimes[drone_id]
        if rt.enabled:
            return
        if rt.lost:
            # A lost aircraft is recovered by maintenance reset only.
            await self.log(
                f"{rt.callsign} is not responding and cannot be powered on.",
                level="error", drone_id=drone_id,
                detail="Contact was lost. Run a maintenance reset to put a replacement on a pad.",
            )
            return

        if pad is not None:
            target = site.pad(pad)
            if target is None:
                await self.log(
                    f"{rt.callsign}: no launch pad called {pad}.",
                    level="error", drone_id=drone_id,
                    detail=f"Known pads: {', '.join(site.PAD_BY_DESIGNATOR)}.",
                )
                return
            rt.home_lat, rt.home_lon = target["lat"], target["lon"]

        # Launch only from a pad; checked against actual home, not the designator.
        area = site.in_launch_area(rt.home_lat, rt.home_lon)
        if area is None:
            await self.log(
                f"{rt.callsign}: home is not on a launch pad.",
                level="error", drone_id=drone_id,
                detail=(
                    f"{rt.home_lat:.5f}, {rt.home_lon:.5f} is not within "
                    f"{site.PAD_RADIUS_M:.0f} m of a pad. Launching is only permitted "
                    f"from {', '.join(site.PAD_BY_DESIGNATOR)}."
                ),
            )
            return

        rt.enabled = True
        rt.state = "BOOTING"
        rt.req_state = "IDLE"
        if rt.alive_since is None:
            rt.alive_since = _now().isoformat()
        await self.log(
            f"Powering on {rt.callsign} on {area.get('designator', 'the pad')}…",
            level="cmd", drone_id=drone_id,
        )
        try:
            await self.drone.power(
                drone_id, True, home=(rt.home_lat, rt.home_lon, rt.home_alt)
            )
        except Exception as exc:  # noqa: BLE001
            await self.log(
                f"Could not power on {rt.callsign}: the drone service did not accept the request.",
                level="error", drone_id=drone_id,
                detail=f"POST {settings.drone_api_url}/drones/{drone_id}/power - {type(exc).__name__}: {exc}",
            )
        self.links[drone_id] = self._make_link(drone_id)
        self.loops[drone_id] = asyncio.create_task(self._control_loop(drone_id))

    async def power_off(self, drone_id: int) -> None:
        rt = self.runtimes[drone_id]
        rt.enabled = False
        loop = self.loops.pop(drone_id, None)
        if loop is not None:
            loop.cancel()
        link = self.links.pop(drone_id, None)
        if link is not None:
            with contextlib.suppress(Exception):
                await link.disconnect()
        with contextlib.suppress(Exception):
            await self.drone.power(drone_id, False)
        rt.state = "OFFLINE"
        rt.req_state = "IDLE"
        rt.is_armed = False
        rt.in_air = False
        rt.lat = rt.lon = rt.alt = 0.0
        # Re-arm the link watchdog to wait for the first frame.
        rt.telemetry_at = 0.0
        rt.outside_ticks = 0
        rt.inside_ticks = 0
        self.claims.pop(drone_id, None)
        await self.log(f"Powered off {rt.callsign}.", level="cmd", drone_id=drone_id)

    async def maintenance_reset(self, drone_id: int, user: User,
                                pad: str | None = None) -> dict:
        """Restore a drone to a known-good state and power it back up.

        Clears tampered MAVLink state on the drone service and this side's
        runtime, logging each step. Never touches the audit log or IDS alerts.
        """
        rt = self.runtimes[drone_id]
        await self.log(
            f"Maintenance reset requested for {rt.callsign} by {user.username}.",
            level="cmd", drone_id=drone_id,
        )

        steps: list[str] = []

        # 1. Stop flying it: cancel the loop and drop the link.
        loop = self.loops.pop(drone_id, None)
        if loop is not None:
            loop.cancel()
            steps.append("control loop stopped")
        link = self.links.pop(drone_id, None)
        if link is not None:
            with contextlib.suppress(Exception):
                await link.disconnect()
            steps.append("flight link closed")
        rt.enabled = False

        # 2. Scrub the drone service side (params, mission, peers, vehicle).
        cleared: dict = {}
        drone_error: str | None = None
        try:
            cleared = await self.drone.reset(drone_id)
        except Exception as exc:  # noqa: BLE001
            # Carry on: `lost` must still be cleared or the drone stays unrecoverable.
            drone_error = f"{type(exc).__name__}: {exc}"
            await self.log(
                f"{rt.callsign}: the drone service did not accept the reset - "
                "clearing this side anyway.",
                level="warn", drone_id=drone_id,
                detail=f"POST {settings.drone_api_url}/drones/{drone_id}/reset - {drone_error}",
            )

        detail = cleared.get("cleared") or {}
        restored = detail.get("params_restored") or []
        if restored:
            steps.append(f"{len(restored)} tampered parameter(s) restored: {', '.join(restored)}")
        if detail.get("mission_upload_discarded"):
            steps.append("discarded a partial mission upload")
        peers = detail.get("peers_dropped") or 0
        if peers:
            steps.append(f"dropped {peers} telemetry subscriber(s) from the radio link")

        # 3. Clear our own runtime state.
        rt.state = "OFFLINE"
        rt.req_state = "IDLE"
        rt.is_armed = False
        rt.in_air = False
        rt.lat = rt.lon = rt.alt = 0.0
        rt.telemetry_at = 0.0
        rt.vx = rt.vy = rt.vz = rt.yaw = 0.0
        rt.target_lat = rt.target_lon = 0.0
        rt.patrol_points = []
        rt.patrol_index = 0
        rt.outside_ticks = 0
        rt.inside_ticks = 0
        self.claims.pop(drone_id, None)

        if rt.lost:
            rt.lost = False
            rt.loss_cause = None
            rt.loss_object_id = None
            rt.last_known_lat = rt.last_known_lon = rt.last_known_alt = None
            rt.last_contact = None
            # New airframe: restart the public status API's alive clock.
            rt.alive_since = _now().isoformat()
            steps.append("replacement airframe signed out of stores")

        # Relocation: put the replacement on the requested pad.
        target = site.pad(pad) if pad else site.in_launch_area(rt.home_lat, rt.home_lon)
        if target is None:
            target = site.pad(site.DEFAULT_PAD)
        if target is not None:
            moved = site.metres_between(rt.home_lat, rt.home_lon, target["lat"], target["lon"]) > 1.0
            rt.home_lat, rt.home_lon = target["lat"], target["lon"]
            steps.append(
                f"aircraft {'relocated to' if moved else 'positioned on'} "
                f"{target.get('designator', 'the pad')}"
            )
        steps.append("runtime state, patrol route and claim cleared")

        for step in steps:
            await self.log(f"  · {step}", drone_id=drone_id)

        await self.audit(user, drone_id, "MAINTENANCE_RESET", {"steps": steps})

        # 4. Power back up.
        await self.power_on(drone_id, pad=target.get("designator") if target else None)

        await self.log(
            f"{rt.callsign} reset complete - powering back up.",
            level="cmd", drone_id=drone_id,
        )
        out: dict = {"ok": True, "steps": steps}
        if drone_error:
            out["drone_service_error"] = drone_error
        return out

    def _make_link(self, drone_id: int) -> DroneLink:
        rt = self.runtimes[drone_id]
        if settings.drone_backend == "px4":
            from app.dronelink.mavsdk_link import MavsdkLink

            # Per-drone port offset (zero for the default single drone).
            port = settings.drone_mavlink_port + drone_id
            # mavsdk_server v2.12 rejects `udpin://`; `udp://:{port}` binds 0.0.0.0.
            return MavsdkLink(
                rt, self.log, f"udp://:{port}", 50050 + drone_id,
                on_failure=self._on_failure,
            )
        return MockLink(rt, self.log, settings.drone_ws_url, on_failure=self._on_failure)

    async def _on_failure(self, drone_id: int) -> None:
        await self.log(
            f"Watchdog: {self.runtimes[drone_id].callsign} hit a critical failure - powering off.",
            level="error", drone_id=drone_id,
            detail="Run a maintenance reset to return it to a known-good state.",
        )
        # Detached: this runs in the link's reader task, which power_off() cancels.
        self._track(asyncio.create_task(self.power_off(drone_id)))

    # ── control loop (state machine) ─────────────────────
    async def _control_loop(self, drone_id: int) -> None:
        rt = self.runtimes[drone_id]
        link = self.links[drone_id]
        ok = False
        with contextlib.suppress(Exception):
            ok = await asyncio.wait_for(link.connect(), timeout=120.0)
        if not ok:
            await self.log(
                f"{rt.callsign}: flight link never came up - standing down.",
                level="error", drone_id=drone_id,
                detail=(
                    f"{link.describe()} did not connect within 120s. "
                    "Check the drone service is running and reachable, then run a maintenance reset."
                ),
            )
            rt.enabled = False
            rt.state = "OFFLINE"
            return

        rt.state = "IDLE"
        rt.req_state = "IDLE"
        await self.log(f"{rt.callsign} ready on the pad, awaiting orders.", drone_id=drone_id)
        tick = 0
        while rt.enabled:
            try:
                if await self._check_link(rt, link):
                    break
                if rt.req_state != rt.state:
                    await self._transition(rt, link)
                await self._tick(rt, link)
            except Exception as exc:  # noqa: BLE001
                await self.log(
                    f"{rt.callsign}: control loop error while {rt.state}.",
                    level="error", drone_id=drone_id,
                    detail=f"{type(exc).__name__}: {exc}",
                )
            tick += 1
            await asyncio.sleep(0.1)

    async def _transition(self, rt: DroneRuntime, link: DroneLink) -> None:
        old, new = rt.state, rt.req_state
        rt.state = new
        await self.log(f"{rt.callsign}: {old} → {new}", level="cmd", drone_id=rt.id)

        if new == "TAKEOFF":
            await link.arm()
            rt.yaw_angle = rt.heading
            await link.set_velocity_ned(0.0, 0.0, -4.0, rt.yaw_angle)
        elif new == "GOTO":
            target_abs = (rt.abs_alt - rt.alt) + rt.target_alt
            await link.goto_location(rt.target_lat, rt.target_lon, target_abs, 0.0)
        elif new == "PATROL":
            await self._fly_to_patrol_leg(rt, link)
        elif new == "HOVER":
            rt.yaw_angle = rt.heading
            await link.hold()
        elif new == "LAND":
            await link.land()
        elif new == "MANUAL":
            rt.yaw_angle = rt.heading
            await link.set_velocity_ned(0.0, 0.0, 0.0, rt.yaw_angle)

    async def _signal_lost(self, rt: DroneRuntime, link: DroneLink,
                           cause: str, obj_id: str | None = None) -> None:
        """Mark the aircraft lost and report only the last known fix.

        Collision, boundary breach and link loss produce identical output; the
        cause is recorded on the runtime for the status API only.
        """
        rt.lost = True
        rt.loss_cause = cause
        rt.loss_object_id = obj_id
        rt.last_known_lat, rt.last_known_lon, rt.last_known_alt = rt.lat, rt.lon, rt.alt
        rt.last_contact = _now().isoformat()
        rt.state = "SIGNAL_LOST"

        ref = site.grid_ref(rt.lat, rt.lon)
        where = f"{rt.lat:.5f}, {rt.lon:.5f}" + (f" (grid {ref})" if ref else "")

        await self.log(
            f"{rt.callsign} - SIGNAL LOST.",
            level="error", drone_id=rt.id,
            detail=f"Last known position {where} at {rt.alt:.0f} m. Position now unknown.",
        )

        # The audit trail records the fix only, never the cause.
        await self.audit(None, rt.id, "SIGNAL_LOST", {
            "last_known_lat": round(rt.lat, 6),
            "last_known_lon": round(rt.lon, 6),
            "last_known_alt_m": round(rt.alt, 1),
            "grid_ref": ref,
            "ground_speed_ms": round(rt.ground_speed, 1),
            "heading_deg": round(rt.heading, 1),
        })

        with contextlib.suppress(Exception):
            await link.land()

        # Decoy console noise, so the useful fix is found in the audit log.
        task = asyncio.create_task(self._signal_loss_chatter(rt))
        self._track(task)
        task = asyncio.create_task(self.power_off(rt.id))
        self._track(task)

    async def _signal_loss_chatter(self, rt: DroneRuntime) -> None:
        """The noise that follows a lost link."""
        messages = [
            ("Telemetry stream interrupted - no frames received.", "warn"),
            (f"{rt.callsign}: no heartbeat for 2 s.", "warn"),
            ("Attempting to re-establish the command link…", "info"),
            (f"{rt.callsign}: position unknown.", "error"),
            ("Link re-acquisition failed (1/3).", "warn"),
            (f"{rt.callsign}: no heartbeat for 5 s.", "warn"),
            ("Link re-acquisition failed (2/3).", "warn"),
            ("Last reported fix is stale; dead reckoning unavailable.", "warn"),
            ("Link re-acquisition failed (3/3) - giving up.", "error"),
            (f"{rt.callsign} is not responding. Airframe presumed lost.", "error"),
            ("Maintenance reset required to put a replacement on a pad.", "info"),
        ]
        for text, level in messages:
            await asyncio.sleep(random.uniform(0.6, 1.8))
            await self.log(text, level=level, drone_id=rt.id)

    async def _check_link(self, rt: DroneRuntime, link: DroneLink) -> bool:
        """Lose the aircraft if telemetry has gone stale; True if it was lost.

        Does nothing until the first frame arrives (telemetry_at == 0.0).
        """
        if rt.lost or not rt.enabled or rt.telemetry_at == 0.0:
            return False
        stale = time.monotonic() - rt.telemetry_at
        if stale < LINK_TIMEOUT_S:
            return False
        await self.log(
            f"{rt.callsign}: no telemetry for {stale:.0f}s.",
            level="error", drone_id=rt.id,
        )
        await self._signal_lost(rt, link, cause="link_lost")
        return True

    async def _check_boundary(self, rt: DroneRuntime, link: DroneLink) -> bool:
        """Lose the aircraft if it has left the site boundary polygon; True if it was lost."""
        if rt.lost:
            return True
        # lat/lon of exactly 0 means "no telemetry yet".
        if not airborne(rt) or (rt.lat == 0.0 and rt.lon == 0.0):
            rt.outside_ticks = 0
            return False

        if site.inside_boundary(rt.lat, rt.lon):
            rt.outside_ticks = 0
            return False

        # Debounce: a single bad frame must not destroy the aircraft.
        rt.outside_ticks += 1
        if rt.outside_ticks < BOUNDARY_BREACH_TICKS:
            return False

        await self._signal_lost(rt, link, cause="out_of_area")
        return True

    def _update_speed(self, rt: DroneRuntime) -> None:
        """Derive ground speed (m/s) from successive positions, independent of backend."""
        now = _now().timestamp()
        prev = self._last_fix.get(rt.id)
        if prev is not None:
            plat, plon, pt = prev
            dt = now - pt
            if dt >= 0.5:
                dist = swarm.horizontal_distance_m(rt.lat, rt.lon, plat, plon)
                rt.ground_speed = dist / dt
                self._last_fix[rt.id] = (rt.lat, rt.lon, now)
        else:
            self._last_fix[rt.id] = (rt.lat, rt.lon, now)

    async def _check_collision(self, rt: DroneRuntime, link: DroneLink) -> bool:
        """Lose the aircraft if it is inside a structure; True if it was lost.

        Altitude is relative to ground, so only structures taller than it count.
        """
        if rt.lost:
            return True
        if not airborne(rt) or (rt.lat == 0.0 and rt.lon == 0.0):
            rt.inside_ticks = 0
            return False

        # Exempt the climb-out from a pad (a helicopter is parked on HP-1).
        if site.on_a_pad(rt.lat, rt.lon, rt.alt):
            rt.inside_ticks = 0
            return False

        ob = site.obstacle_at(rt.lat, rt.lon, rt.alt)
        if ob is None:
            rt.inside_ticks = 0
            return False

        rt.inside_ticks += 1
        if rt.inside_ticks < COLLISION_TICKS:
            return False

        await self._signal_lost(rt, link, cause="collision", obj_id=ob["id"])
        return True

    async def _tick(self, rt: DroneRuntime, link: DroneLink) -> None:
        self._update_speed(rt)
        if await self._check_boundary(rt, link):
            return
        if await self._check_collision(rt, link):
            return
        state = rt.state
        if state == "TAKEOFF":
            remaining = rt.target_alt - rt.alt
            if remaining <= TAKEOFF_TOLERANCE_M:
                await self.log(f"{rt.callsign} reached altitude, holding.", drone_id=rt.id)
                rt.req_state = "HOVER"
            else:
                # Slow the climb over the last 6 m to avoid overshoot.
                climb = -4.0 if remaining > 6.0 else -1.0
                await link.set_velocity_ned(0.0, 0.0, climb, rt.yaw_angle)
        elif state == "GOTO":
            dist = swarm.horizontal_distance_m(rt.lat, rt.lon, rt.target_lat, rt.target_lon)
            if dist < 2.0 and abs(rt.alt - rt.target_alt) < 2.0:
                await self.log(f"{rt.callsign} arrived at destination, holding.", drone_id=rt.id)
                rt.req_state = "HOVER"
            else:
                await self._assert_target(rt, link)
        elif state == "PATROL":
            if not rt.patrol_points:
                rt.req_state = "HOVER"
                return
            dist = swarm.horizontal_distance_m(rt.lat, rt.lon, rt.target_lat, rt.target_lon)
            if dist < PATROL_ARRIVE_M:
                # Advance to the next waypoint, looping.
                rt.patrol_index = (rt.patrol_index + 1) % len(rt.patrol_points)
                await self._fly_to_patrol_leg(rt, link)
            else:
                await self._assert_target(rt, link)
        elif state == "HOVER":
            await link.set_velocity_ned(0.0, 0.0, 0.0, rt.yaw_angle)
        elif state == "LAND":
            if not rt.is_armed:
                await self.log(f"{rt.callsign} touched down, idle.", drone_id=rt.id)
                rt.state = "IDLE"
                rt.req_state = "IDLE"
        elif state == "MANUAL":
            down = rt.vz
            if rt.alt < 1.0 and down > 0:  # NED: positive is down
                down = 0.0
            rt.yaw_angle = (rt.yaw_angle + rt.yaw * 0.1) % 360
            await link.set_velocity_ned(rt.vx, rt.vy, down, rt.yaw_angle)

    async def _assert_target(self, rt: DroneRuntime, link: DroneLink) -> None:
        """Re-send the current position setpoint.

        PX4 drops out of offboard without a setpoint stream faster than 2 Hz
        and lands on failsafe, so the position modes re-assert their target on
        every tick exactly as the velocity modes do. It also means a new target
        reaches the aircraft without needing a state change.
        """
        target_abs = (rt.abs_alt - rt.alt) + rt.target_alt
        await link.goto_location(rt.target_lat, rt.target_lon, target_abs, 0.0)

    async def _fly_to_patrol_leg(self, rt: DroneRuntime, link: DroneLink) -> None:
        """Send the drone to the current patrol waypoint."""
        if not rt.patrol_points:
            return
        lat, lon = rt.patrol_points[rt.patrol_index]
        rt.target_lat, rt.target_lon = lat, lon
        target_abs = (rt.abs_alt - rt.alt) + rt.target_alt
        await self.log(
            f"Drone {rt.id} sentinel → waypoint {rt.patrol_index + 1}/{len(rt.patrol_points)}"
        )
        await link.goto_location(lat, lon, target_abs, 0.0)

    # ── command application ──────────────────────────────
    async def apply_command(self, drone_id: int, command: str, params: dict, user: User) -> tuple[bool, str]:
        rt = self.runtimes.get(drone_id)
        if rt is None or not rt.enabled:
            return False, "drone offline"

        audit_action: str | None = None
        if command == "CANCEL":
            rt.req_state = "HOVER"
            rt.patrol_points = []  # also stops any patrol
            audit_action = "CANCEL"
        elif command == "PATROL":
            pts = params.get("points") or []
            waypoints = [
                (float(p["lat"]), float(p["lon"]))
                for p in pts
                if isinstance(p, dict) and "lat" in p and "lon" in p
            ]
            if params.get("swarm_mode"):
                waypoints = [swarm.apply_swarm_offset(drone_id, la, lo) for la, lo in waypoints]
            if len(waypoints) < 2:
                return False, "patrol needs at least 2 points"
            rt.patrol_points = waypoints
            rt.patrol_index = 0
            rt.req_state = "PATROL"
            audit_action = "PATROL"
        elif command == "ALTITUDE":
            # Change altitude without re-planning the route.
            new_alt = params.get("target_alt", params.get("alt"))
            if new_alt is None:
                return False, "altitude required"
            rt.target_alt = max(0.0, float(new_alt))
            audit_action = "ALTITUDE"
            link = self.links.get(drone_id)
            if rt.state == "PATROL" and rt.patrol_points and link is not None:
                # Re-issue the current leg at the new altitude.
                await self._fly_to_patrol_leg(rt, link)
            elif rt.state == "GOTO" and link is not None:
                target_abs = (rt.abs_alt - rt.alt) + rt.target_alt
                await link.goto_location(rt.target_lat, rt.target_lon, target_abs, 0.0)
            elif airborne(rt) and rt.state in {"HOVER", "IDLE"}:
                # HOVER re-asserts zero velocity each tick, which would cancel a
                # climb; GOTO the current position instead.
                rt.target_lat, rt.target_lon = rt.lat, rt.lon
                rt.req_state = "GOTO"
            # On the ground this only sets the next takeoff altitude.
            where = "climbing to" if rt.target_alt > rt.alt else "descending to"
            await self.log(
                f"{rt.callsign}: {where} {rt.target_alt:.0f} m."
                if airborne(rt) else
                f"{rt.callsign}: takeoff altitude set to {rt.target_alt:.0f} m.",
                level="cmd", drone_id=drone_id,
            )
        elif command in {"TAKEOFF", "GOTO", "LAND", "HOVER", "MANUAL"}:
            rt.req_state = command
            if command != "MANUAL" or not params.get("_stream"):
                audit_action = command

        if "target_alt" in params:
            rt.target_alt = float(params["target_alt"])
        if "target_lat" in params and "target_lon" in params:
            t_lat = float(params["target_lat"])
            t_lon = float(params["target_lon"])
            if params.get("swarm_mode"):
                t_lat, t_lon = swarm.apply_swarm_offset(drone_id, t_lat, t_lon)
            rt.target_lat, rt.target_lon = t_lat, t_lon

        if rt.req_state == "MANUAL":
            for axis in ("vx", "vy", "vz", "yaw"):
                if axis in params:
                    setattr(rt, axis, float(params[axis]))

        self.touch_claim(drone_id)

        if audit_action:
            clean = {k: v for k, v in params.items() if not k.startswith("_")}
            await self.audit(user, drone_id, audit_action, clean)
        return True, "ok"

    # ── claims (in-memory, TTL-based) ────────────────────
    def get_claim(self, drone_id: int) -> ClaimRecord | None:
        rec = self.claims.get(drone_id)
        if rec is not None and rec.expires_at <= _now():
            self.claims.pop(drone_id, None)
            return None
        return rec

    def can_command(self, drone_id: int, user: User) -> bool:
        if user.role == Role.admin:
            return True
        rec = self.get_claim(drone_id)
        return rec is not None and rec.user_id == user.id

    def touch_claim(self, drone_id: int) -> None:
        rec = self.claims.get(drone_id)
        if rec is not None:
            rec.expires_at = _now() + timedelta(seconds=settings.claim_ttl_seconds)

    async def acquire_claim(self, drone_id: int, user: User) -> tuple[bool, ClaimRecord | None]:
        rec = self.get_claim(drone_id)
        if rec is not None and rec.user_id != user.id:
            return False, rec
        self.claims[drone_id] = ClaimRecord(
            user_id=user.id, username=user.username,
            acquired_at=_now(), expires_at=_now() + timedelta(seconds=settings.claim_ttl_seconds),
        )
        await self.audit(user, drone_id, "CLAIM", {})
        return True, self.claims[drone_id]

    async def release_claim(self, drone_id: int, user: User, force: bool = False) -> bool:
        rec = self.get_claim(drone_id)
        if rec is None:
            return True
        if not force and user.role != Role.admin and rec.user_id != user.id:
            return False
        self.claims.pop(drone_id, None)
        action = "FORCE_RELEASE" if force and rec.user_id != user.id else "RELEASE"
        await self.audit(user, drone_id, action, {"previous_holder": rec.username})
        return True

    # ── audit ────────────────────────────────────────────
    async def audit(self, user: User | None, drone_id: int | None, action: str, params: dict, result: str = "ok") -> None:
        async with AsyncSessionLocal() as session:
            session.add(AuditLog(
                ts=_now(),
                user_id=user.id if user else None,
                username=user.username if user else "",
                drone_id=drone_id,
                action=action,
                params=params or {},
                result=result,
            ))
            await session.commit()

    # ── background loops ─────────────────────────────────
    async def _broadcast_loop(self) -> None:
        while True:
            if self.manager.active:
                await self.manager.broadcast(self._telemetry_payload())
            await asyncio.sleep(0.1)

    def _telemetry_payload(self) -> str:
        drones = {}
        for drone_id, rt in self.runtimes.items():
            rec = self.get_claim(drone_id)
            drones[drone_id] = {
                "enabled": rt.enabled,
                "state": rt.state if rt.enabled else "OFFLINE",
                "lat": rt.lat,
                "lon": rt.lon,
                "alt": rt.alt,
                "heading": rt.heading,
                "armed": rt.is_armed,
                "speed": round(rt.ground_speed, 2),
                "lost": rt.lost,
                "last_known_lat": rt.last_known_lat,
                "last_known_lon": rt.last_known_lon,
                "last_known_alt": rt.last_known_alt,
                "last_contact": rt.last_contact,
                # Current target and route, visible to every connected user.
                "target": (
                    {"lat": rt.target_lat, "lon": rt.target_lon, "alt": rt.target_alt}
                    if rt.state in ("GOTO", "PATROL")
                    and not (rt.target_lat == 0.0 and rt.target_lon == 0.0)
                    else None
                ),
                "patrol": (
                    {
                        "points": [[lat, lon] for lat, lon in rt.patrol_points],
                        "index": rt.patrol_index,
                    }
                    if rt.patrol_points
                    else None
                ),
                "claim": {
                    "held": rec is not None,
                    "user_id": rec.user_id if rec else None,
                    "username": rec.username if rec else None,
                },
            }
        return json.dumps({"type": "telemetry", "drones": drones})

    async def _claim_keeper_loop(self) -> None:
        """Refresh claims whose holder is connected; others expire."""
        while True:
            connected = self.manager.connected_user_ids()
            for rec in list(self.claims.values()):
                if rec.user_id in connected:
                    rec.expires_at = _now() + timedelta(seconds=settings.claim_ttl_seconds)
            await asyncio.sleep(min(15, max(2, settings.claim_ttl_seconds // 4)))

    async def _telemetry_persist_loop(self) -> None:
        while True:
            await asyncio.sleep(5.0)
            enabled = [rt for rt in self.runtimes.values() if rt.enabled and rt.lat != 0.0]
            if not enabled:
                continue
            async with AsyncSessionLocal() as session:
                for rt in enabled:
                    session.add(TelemetrySample(
                        drone_id=rt.id, ts=_now(), lat=rt.lat, lon=rt.lon,
                        alt=rt.alt, heading=rt.heading, state=rt.state,
                    ))
                await session.commit()


fleet = FleetService()
