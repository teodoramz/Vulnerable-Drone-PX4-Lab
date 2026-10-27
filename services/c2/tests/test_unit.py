from datetime import datetime, timedelta, timezone

from app.core.rbac import Permission, Role, has_permission
from app.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.dronelink.base import DroneLink, DroneRuntime
from app.schemas.ids import IdsAlertIn
from app.services import swarm
from app.services.fleet import FleetService, airborne
from app.services.ids import IdsService


# ── fakes ────────────────────────────────────────────────
class _User:
    def __init__(self, uid: int, username: str, role: Role):
        self.id = uid
        self.username = username
        self.role = role


class FakeLink(DroneLink):
    def __init__(self, rt, log):
        super().__init__(rt, log)
        self.calls: list = []

    async def connect(self):
        return True

    async def disconnect(self):
        pass

    async def arm(self):
        self.calls.append(("arm",))

    async def set_velocity_ned(self, n, e, d, yaw):
        self.calls.append(("vel", n, e, d, yaw))

    async def goto_location(self, lat, lon, alt, yaw):
        self.calls.append(("goto", lat, lon, alt, yaw))

    async def land(self):
        self.calls.append(("land",))

    async def hold(self):
        self.calls.append(("hold",))


def _fleet_with_drone(monkeypatch, enabled=True):
    fleet = FleetService()
    rt = DroneRuntime(0, "Alpha", 47.4, 8.5, 488.0)
    rt.enabled = enabled
    fleet.runtimes[0] = rt

    async def _noaudit(*a, **k):
        pass

    monkeypatch.setattr(fleet, "audit", _noaudit)
    return fleet, rt


# ── security ─────────────────────────────────────────────
def test_password_hashing():
    h = hash_password("s3cret")
    assert h != "s3cret"
    assert verify_password("s3cret", h)
    assert not verify_password("wrong", h)


def test_token_roundtrip():
    token = create_access_token(subject="bob", user_id=5, role="operator")
    payload = decode_token(token)
    assert payload["sub"] == "bob"
    assert payload["uid"] == 5
    assert payload["role"] == "operator"


# ── rbac ─────────────────────────────────────────────────
def test_permission_matrix():
    assert has_permission(Role.admin, Permission.USER_MANAGE)
    assert has_permission(Role.operator, Permission.DRONE_COMMAND)
    assert not has_permission(Role.observer, Permission.DRONE_COMMAND)
    assert has_permission(Role.observer, Permission.DRONE_READ)
    assert not has_permission(Role.operator, Permission.USER_MANAGE)
    assert not has_permission(Role.operator, Permission.DRONE_FORCE_RELEASE)


# ── swarm math ───────────────────────────────────────────
def test_airborne_does_not_wait_for_the_in_air_subscription():
    """A hover at altitude counts as airborne even before `in_air` arrives.

    `in_air` is its own MAVSDK telemetry subscription and can still read false
    when the control loop already reports HOVER. Gating on it alone made an
    ALTITUDE command a silent no-op and left the boundary and collision checks
    off during climb-out.
    """
    rt = DroneRuntime(id=0, callsign="Sentinel", home_lat=44.0, home_lon=25.0, home_alt=95.0)

    rt.state, rt.alt, rt.in_air = "IDLE", 0.0, False
    assert not airborne(rt), "sitting on the pad is not airborne"

    rt.state, rt.alt = "HOVER", 50.0
    assert airborne(rt), "a hover at 50 m is airborne whatever in_air says"

    rt.state, rt.alt = "TAKEOFF", 0.4
    assert not airborne(rt), "still on the pad during the first metre"

    rt.in_air = True
    assert airborne(rt), "the subscription alone is enough once it arrives"

    rt.in_air, rt.state, rt.alt = False, "OFFLINE", 0.0
    assert not airborne(rt), "a powered-off airframe is not airborne"


def test_swarm_offsets():
    assert swarm.swarm_lateral_offset(0) == 0.0
    assert swarm.swarm_lateral_offset(1) == 3.0
    assert swarm.swarm_lateral_offset(2) == -3.0
    lat, lon = swarm.apply_swarm_offset(1, 47.4, 8.5)
    assert lat == 47.4 and lon > 8.5
    assert swarm.horizontal_distance_m(47.4, 8.5, 47.4, 8.5) == 0.0
    assert swarm.horizontal_distance_m(47.4, 8.5, 47.401, 8.5) > 100


# ── claim / lock arbitration ─────────────────────────────
async def test_claim_arbitration(monkeypatch):
    fleet, _ = _fleet_with_drone(monkeypatch)
    alice = _User(1, "alice", Role.operator)
    bob = _User(2, "bob", Role.operator)
    admin = _User(3, "root", Role.admin)

    ok, _ = await fleet.acquire_claim(0, alice)
    assert ok
    assert fleet.can_command(0, alice)
    assert not fleet.can_command(0, bob)
    assert fleet.can_command(0, admin)  # admin override

    ok, holder = await fleet.acquire_claim(0, bob)
    assert not ok and holder.user_id == alice.id

    assert not await fleet.release_claim(0, bob)        # not the holder
    assert await fleet.release_claim(0, bob, force=True)  # force/admin path
    assert fleet.get_claim(0) is None


async def _noop_audit(*args, **kwargs) -> None:
    """Audit stub (the real one writes to the database)."""
    return None

async def test_claim_expiry(monkeypatch):
    fleet, _ = _fleet_with_drone(monkeypatch)
    alice = _User(1, "alice", Role.operator)
    await fleet.acquire_claim(0, alice)
    fleet.claims[0].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert fleet.get_claim(0) is None
    assert not fleet.can_command(0, alice)


# ── flight state machine ─────────────────────────────────
async def test_takeoff_reaches_hover(monkeypatch):
    fleet, rt = _fleet_with_drone(monkeypatch)
    rt.state = "TAKEOFF"
    rt.target_alt = 10.0
    rt.alt = 9.5
    await fleet._tick(rt, FakeLink(rt, fleet.log))
    assert rt.req_state == "HOVER"


async def test_goto_arrival(monkeypatch):
    fleet, rt = _fleet_with_drone(monkeypatch)
    rt.state = "GOTO"
    rt.lat = rt.target_lat = 47.4
    rt.lon = rt.target_lon = 8.5
    rt.alt = rt.target_alt = 12.0
    await fleet._tick(rt, FakeLink(rt, fleet.log))
    assert rt.req_state == "HOVER"


async def test_land_to_idle(monkeypatch):
    fleet, rt = _fleet_with_drone(monkeypatch)
    rt.state = "LAND"
    rt.is_armed = False
    await fleet._tick(rt, FakeLink(rt, fleet.log))
    assert rt.state == "IDLE"


async def test_apply_command_gating(monkeypatch):
    fleet, rt = _fleet_with_drone(monkeypatch, enabled=False)
    alice = _User(1, "alice", Role.operator)
    ok, _ = await fleet.apply_command(0, "TAKEOFF", {"target_alt": 10}, alice)
    assert not ok  # offline drone rejected

    rt.enabled = True
    ok, _ = await fleet.apply_command(0, "TAKEOFF", {"target_alt": 15}, alice)
    assert ok and rt.req_state == "TAKEOFF" and rt.target_alt == 15.0


async def test_goto_reasserts_its_setpoint_every_tick(monkeypatch):
    """PX4 leaves offboard without a >2 Hz setpoint stream and lands.

    The position modes used to send one setpoint on the state transition and
    nothing after, so the aircraft fell out of offboard mid-flight and PX4
    landed it on failsafe. A new target also never reached the vehicle,
    because GOTO -> GOTO runs no transition.
    """
    fleet, rt = _fleet_with_drone(monkeypatch)
    link = FakeLink(rt, fleet.log)
    fleet.links[0] = link

    rt.state = "GOTO"
    rt.alt, rt.abs_alt = 100.0, 588.0
    rt.lat, rt.lon = 47.4, 8.5
    rt.target_lat, rt.target_lon, rt.target_alt = 47.5, 8.6, 120.0

    await fleet._tick(rt, link)
    gotos = [c for c in link.calls if c[0] == "goto"]
    assert gotos, "no setpoint sent while in GOTO: offboard would time out"
    assert gotos[-1][1] == 47.5 and gotos[-1][2] == 8.6
    # abs_alt - alt is the ground reference; the target is 120 m above it.
    assert abs(gotos[-1][3] - 608.0) < 1e-6

    # A re-target reaches the aircraft on the next tick, with no state change.
    rt.target_lat, rt.target_lon = 47.6, 8.7
    await fleet._tick(rt, link)
    gotos = [c for c in link.calls if c[0] == "goto"]
    assert gotos[-1][1] == 47.6 and gotos[-1][2] == 8.7


async def test_goto_stops_asserting_once_it_arrives(monkeypatch):
    """Arrival hands over to HOVER instead of streaming the target forever."""
    fleet, rt = _fleet_with_drone(monkeypatch)
    link = FakeLink(rt, fleet.log)
    fleet.links[0] = link

    rt.state = "GOTO"
    rt.alt, rt.abs_alt = 120.0, 608.0
    rt.lat, rt.lon = 47.5, 8.6
    rt.target_lat, rt.target_lon, rt.target_alt = 47.5, 8.6, 120.0

    await fleet._tick(rt, link)
    assert rt.req_state == "HOVER"
    assert not [c for c in link.calls if c[0] == "goto"]


# ── IDS alerts ────────────────────────────────────────────
def _alert(sid: int, severity: int = 1, signature: str = "test-sig") -> IdsAlertIn:
    return IdsAlertIn(
        ts="2026-09-21T00:00:00Z",
        signature=signature,
        sid=sid,
        severity=severity,
        category="test",
        src_ip="10.0.0.1",
        src_port=1234,
        dest_ip="10.0.0.2",
        dest_port=14550,
        proto="UDP",
        iface="eth0",
    )


async def test_ids_ring_buffer_evicts_oldest():
    svc = IdsService(cap=3)
    for i in range(5):
        await svc.ingest(_alert(sid=i, signature=f"sig-{i}"))
    kept = [a["sid"] for a in svc.recent(limit=10)]
    assert len(kept) == 3
    assert kept == [2, 3, 4]  # oldest two (0, 1) evicted


async def test_ids_severity_filter_and_limit():
    svc = IdsService(cap=100)
    await svc.ingest(_alert(sid=1, severity=1))
    await svc.ingest(_alert(sid=2, severity=3))
    await svc.ingest(_alert(sid=3, severity=3))

    only_high = svc.recent(limit=10, severity=3)
    assert {a["sid"] for a in only_high} == {2, 3}

    limited = svc.recent(limit=1)
    assert len(limited) == 1
    assert limited[0]["sid"] == 3  # most recent kept when limiting


async def test_seed_reconciles_registry_down_to_drone_count():
    """Seed makes DRONE_COUNT authoritative when the registry has extra drones."""
    from sqlalchemy import select

    from app.config import settings
    from app.db.base import AsyncSessionLocal
    from app.models.drone import Drone
    from app.seed import seed

    # three drones on the old callsign scheme
    async with AsyncSessionLocal() as session:
        for d in (await session.execute(select(Drone))).scalars().all():
            await session.delete(d)
        await session.flush()
        for i, name in enumerate(["Alpha", "Bravo", "Charlie"]):
            session.add(Drone(id=i, callsign=name, model="x500",
                              home_lat=1.0, home_lon=2.0, home_alt=3.0))
        await session.commit()

    original = settings.drone_count
    settings.drone_count = 1
    try:
        await seed()
        async with AsyncSessionLocal() as session:
            drones = (await session.execute(select(Drone).order_by(Drone.id))).scalars().all()
        assert len(drones) == 1, f"expected the fleet to shrink to 1, got {len(drones)}"
        assert drones[0].callsign == "Sentinel"
        assert drones[0].home_lat == settings.home_lat
    finally:
        settings.drone_count = original


async def test_seed_reconciles_registry_up_to_drone_count():
    """Seed grows the registry when DRONE_COUNT is raised."""
    from sqlalchemy import select

    from app.config import settings
    from app.db.base import AsyncSessionLocal
    from app.models.drone import Drone
    from app.seed import seed

    original = settings.drone_count
    settings.drone_count = 3
    try:
        await seed()
        async with AsyncSessionLocal() as session:
            drones = (await session.execute(select(Drone).order_by(Drone.id))).scalars().all()
        assert [d.callsign for d in drones] == ["Sentinel", "Vigil", "Warden"]
    finally:
        settings.drone_count = original
        await seed()


async def test_external_disarm_while_airborne_is_detected():
    """An arm->disarm transition while flying marks ERROR and trips the failure hook."""
    import json

    from app.dronelink.base import DroneRuntime
    from app.dronelink.mock_link import MockLink

    rt = DroneRuntime(id=0, callsign="Sentinel", home_lat=43.9977991, home_lon=25.0154851, home_alt=95.0)
    rt.state = "PATROL"
    rt.is_armed = True

    logs: list[str] = []
    failed: list[int] = []

    async def log(m): logs.append(m)
    async def on_failure(i): failed.append(i)

    link = MockLink(rt, log, "ws://unused", on_failure=on_failure)

    class FakeWS:
        """Yields one disarmed telemetry frame."""
        def __aiter__(self): return self
        async def __anext__(self):
            if getattr(self, "_sent", False):
                raise StopAsyncIteration
            self._sent = True
            return json.dumps({
                "type": "telemetry", "drone_id": 0,
                "lat": 44.32, "lon": 28.05, "rel_alt": 30.0, "abs_alt": 55.0,
                "heading": 90.0, "armed": False, "in_air": True,
            })

    link.ws = FakeWS()
    await link._read_loop()

    assert rt.state == "ERROR", f"expected ERROR, got {rt.state}"
    assert failed == [0], "the failure hook did not fire"
    assert any("external command" in m for m in logs), logs


async def test_normal_landing_is_not_reported_as_an_attack():
    """A disarm during a commanded LAND is not an attack."""
    import json

    from app.dronelink.base import DroneRuntime
    from app.dronelink.mock_link import MockLink

    rt = DroneRuntime(id=0, callsign="Sentinel", home_lat=43.9977991, home_lon=25.0154851, home_alt=95.0)
    rt.state = "LAND"
    rt.is_armed = True

    failed: list[int] = []
    async def log(m): pass
    async def on_failure(i): failed.append(i)

    link = MockLink(rt, log, "ws://unused", on_failure=on_failure)

    class FakeWS:
        def __aiter__(self): return self
        async def __anext__(self):
            if getattr(self, "_sent", False):
                raise StopAsyncIteration
            self._sent = True
            return json.dumps({
                "type": "telemetry", "drone_id": 0,
                "lat": 44.32, "lon": 28.05, "rel_alt": 0.0, "abs_alt": 25.0,
                "heading": 0.0, "armed": False, "in_air": False,
            })

    link.ws = FakeWS()
    await link._read_loop()

    assert rt.state == "LAND", "a normal landing must not be flagged"
    assert failed == [], "a normal landing must not trip the failure hook"


async def test_watchdog_power_off_completes_despite_self_cancellation():
    """power_off must finish even though disconnect() cancels the reader that invoked the hook."""
    import asyncio

    from app.dronelink.base import DroneRuntime
    from app.services.fleet import FleetService, airborne

    fleet = FleetService()
    rt = DroneRuntime(id=0, callsign="Sentinel", home_lat=43.9977991, home_lon=25.0154851, home_alt=95.0)
    rt.enabled, rt.state, rt.is_armed, rt.in_air = True, "HOVER", True, True
    rt.lat, rt.lon, rt.alt = 44.33, 28.06, 37.0
    fleet.runtimes[0] = rt

    reader_task: asyncio.Task | None = None

    class ReaderCancellingLink:
        """disconnect() cancels the reader task, as the real links do."""
        async def disconnect(self):
            if reader_task is not None:
                reader_task.cancel()
            await asyncio.sleep(0)

    fleet.links[0] = ReaderCancellingLink()

    async def reader():
        await fleet._on_failure(0)
        await asyncio.sleep(3600)

    reader_task = asyncio.create_task(reader())

    # Poll rather than sleep: power_off runs in a detached task.
    deadline = asyncio.get_running_loop().time() + 5.0
    while rt.state != "OFFLINE" and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.01)

    assert reader_task.cancelled() or reader_task.done(), "the reader should have been cancelled"
    assert rt.state == "OFFLINE", f"power_off did not finish; state={rt.state}"
    assert rt.alt == 0.0, f"stale altitude survived power_off: {rt.alt}"
    assert rt.is_armed is False and rt.in_air is False
    assert rt.enabled is False

    await fleet.shutdown()


async def test_log_entries_carry_level_and_detail():
    """Level and detail survive into the broadcast frame."""
    import json

    from app.services.fleet import FleetService, airborne

    fleet = FleetService()
    sent: list[str] = []

    class FakeWS:
        async def send_text(self, payload): sent.append(payload)

    class FakeUser:
        id, username = 1, "admin"

    fleet.manager.connect(FakeWS(), FakeUser())
    await fleet.log("link never came up", level="error", drone_id=0,
                    detail="ws://drone:9100/ws - TimeoutError")

    assert len(fleet.logs) == 1
    entry = json.loads(sent[-1])
    assert entry["type"] == "log"
    assert entry["level"] == "error"
    assert entry["drone_id"] == 0
    assert entry["detail"] == "ws://drone:9100/ws - TimeoutError"
    assert entry["ts"]

    # unknown levels fall back to info
    await fleet.log("odd", level="banana")
    assert json.loads(sent[-1])["level"] == "info"


async def test_maintenance_reset_clears_state_and_powers_back_up():
    """Reset clears runtime state and leaves the drone powered on."""
    from app.dronelink.base import DroneRuntime
    from app.services.fleet import FleetService, airborne

    fleet = FleetService()
    rt = DroneRuntime(id=0, callsign="Sentinel", home_lat=43.9977991, home_lon=25.0154851, home_alt=95.0)
    rt.enabled, rt.state, rt.is_armed, rt.in_air = True, "PATROL", True, True
    rt.lat, rt.lon, rt.alt = 44.33, 28.06, 40.0
    rt.patrol_points = [(44.32, 28.05), (44.33, 28.06)]
    rt.patrol_index = 1
    rt.target_lat, rt.target_lon = 44.34, 28.07
    fleet.runtimes[0] = rt

    class FakeUser:
        id, username, role = 1, "admin", "admin"

    reset_calls, power_calls = [], []

    class FakeDroneClient:
        async def reset(self, drone_id):
            reset_calls.append(drone_id)
            return {"cleared": {"params_restored": ["NAV_DLL_ACT"],
                                "mission_upload_discarded": True,
                                "peers_dropped": 2}}
        async def power(self, drone_id, on):
            power_calls.append((drone_id, on))
        async def aclose(self): pass

    fleet.drone = FakeDroneClient()
    fleet.audit = lambda *a, **k: _noop()

    async def _noop(): return None

    result = await fleet.maintenance_reset(0, FakeUser())

    assert result["ok"] is True
    assert reset_calls == [0], "the drone service was never asked to reset"
    assert rt.patrol_points == [] and rt.patrol_index == 0
    assert rt.target_lat == 0.0 and rt.target_lon == 0.0
    assert rt.is_armed is False and rt.in_air is False
    assert 0 not in fleet.claims

    joined = " ".join(result["steps"])
    assert "NAV_DLL_ACT" in joined, "tampered params not reported to the operator"
    assert "mission upload" in joined
    assert "subscriber" in joined, "attacker peers not reported"

    assert rt.enabled is True, "reset left the drone powered off"

    await fleet.shutdown()


async def test_crossing_the_operational_boundary_loses_the_aircraft():
    """A drone flown outside the operational area is lost and cannot be powered back on."""
    from app.dronelink.base import DroneRuntime
    from app.services import site
    from app.services.fleet import BOUNDARY_BREACH_TICKS, FleetService

    fleet = FleetService()
    rt = DroneRuntime(id=0, callsign="Sentinel",
                      home_lat=site.HOME_LAT, home_lon=site.HOME_LON, home_alt=95.0)
    rt.enabled, rt.state, rt.in_air = True, "GOTO", True
    # north-west corner of the map, outside the polygon
    rt.lat, rt.lon = site.to_latlon(100.0, 100.0)
    rt.alt = 40.0
    fleet.runtimes[0] = rt
    fleet.audit = _noop_audit

    class FakeLink:
        async def land(self): pass

    # debounced over consecutive readings
    for _ in range(BOUNDARY_BREACH_TICKS - 1):
        assert await fleet._check_boundary(rt, FakeLink()) is False, "wrote it off too early"
    assert await fleet._check_boundary(rt, FakeLink()) is True
    assert rt.lost is True
    assert rt.state == "SIGNAL_LOST"
    assert rt.last_known_lat == rt.lat and rt.last_known_lon == rt.lon
    assert rt.last_contact is not None
    assert rt.loss_cause == "out_of_area"

    rt.enabled = False
    await fleet.power_on(0)
    assert rt.enabled is False, "a lost drone was powered back on"

    await fleet.shutdown()


async def test_losing_the_aircraft_never_says_why():
    """Collision and boundary losses produce identical output that never names the cause."""
    from app.dronelink.base import DroneRuntime
    from app.services import site
    from app.services.fleet import FleetService, airborne

    tower = next(o for o in site.OBJECTS if o["type"] == "control_tower")
    audited: list[tuple] = []

    for cause, (lat, lon), obj_id in (
        ("collision", (tower["lat"], tower["lon"]), tower["id"]),
        ("out_of_area", site.to_latlon(100.0, 100.0), None),
    ):
        fleet = FleetService()
        rt = DroneRuntime(id=0, callsign="Sentinel",
                          home_lat=site.HOME_LAT, home_lon=site.HOME_LON, home_alt=95.0)
        rt.enabled, rt.state, rt.in_air = True, "GOTO", True
        rt.lat, rt.lon, rt.alt = lat, lon, 20.0
        fleet.runtimes[0] = rt

        said: list[str] = []

        async def log(msg, level="info", drone_id=None, detail=None):
            said.append(f"{msg} {detail or ''}")

        async def audit(user, drone_id, action, params, result="ok"):
            audited.append((action, params))

        fleet.log = log
        fleet.audit = audit

        class FakeLink:
            async def land(self): pass

        await fleet._signal_lost(rt, FakeLink(), cause=cause, obj_id=obj_id)
        text = " ".join(said).lower()

        for giveaway in ("tower", "crash", "collision", "hit ", "struct",
                         "boundary", "outside", "twr-"):
            assert giveaway not in text, f"{cause}: console leaked {giveaway!r}"
        assert "signal lost" in text

        # the audit trail records the position, not the cause
        action, params = audited[-1]
        assert action == "SIGNAL_LOST"
        assert "last_known_lat" in params and "grid_ref" in params
        assert not any(
            k for k in params if "object" in k or "obstacle" in k or "cause" in k
        ), f"audit leaked the cause: {params}"

        await fleet.shutdown()


async def test_a_dead_link_loses_the_aircraft():
    """Stale telemetry loses the aircraft."""
    import time as _time

    from app.dronelink.base import DroneRuntime
    from app.services import site
    from app.services.fleet import LINK_TIMEOUT_S, FleetService

    fleet = FleetService()
    rt = DroneRuntime(id=0, callsign="Sentinel",
                      home_lat=site.HOME_LAT, home_lon=site.HOME_LON, home_alt=95.0)
    rt.enabled, rt.state, rt.in_air = True, "HOVER", True
    rt.lat, rt.lon, rt.alt = site.HOME_LAT, site.HOME_LON, 40.0
    fleet.runtimes[0] = rt

    said: list[str] = []

    async def log(msg, level="info", drone_id=None, detail=None):
        said.append(str(msg))

    async def audit(user, drone_id, action, params, result="ok"):
        pass

    fleet.log = log
    fleet.audit = audit

    class FakeLink:
        async def land(self): pass

    link = FakeLink()

    # no telemetry yet: not lost
    rt.telemetry_at = 0.0
    assert await fleet._check_link(rt, link) is False
    assert rt.lost is False

    rt.telemetry_at = _time.monotonic()
    assert await fleet._check_link(rt, link) is False
    assert rt.lost is False

    rt.telemetry_at = _time.monotonic() - (LINK_TIMEOUT_S + 1.0)
    assert await fleet._check_link(rt, link) is True
    assert rt.lost is True
    assert rt.state == "SIGNAL_LOST"
    assert rt.loss_cause == "link_lost"
    assert rt.last_known_alt == 40.0

    text = " ".join(said).lower()
    assert "signal lost" in text
    for giveaway in ("crash", "collision", "boundary", "outside", "px4", "process"):
        assert giveaway not in text, f"console leaked {giveaway!r}"

    await fleet.shutdown()


async def test_inside_the_operational_boundary_is_left_alone():
    """Pads and patrol waypoints are inside the boundary; a grounded drone is never lost."""
    from app.dronelink.base import DroneRuntime
    from app.services import site
    from app.services.fleet import FleetService, airborne

    fleet = FleetService()
    rt = DroneRuntime(id=0, callsign="Sentinel",
                      home_lat=site.HOME_LAT, home_lon=site.HOME_LON, home_alt=95.0)
    rt.enabled, rt.state, rt.in_air = True, "PATROL", True

    class FakeLink:
        async def land(self): pass

    # Both pads and every patrol waypoint are inside the area.
    places = [(p["designator"], p["lat"], p["lon"]) for p in site.LAUNCH_PADS]
    for key, route in site.PATROL_ROUTES.items():
        places += [(f"{key}[{i}]", lat, lon) for i, (lat, lon) in enumerate(route["points"])]

    for name, lat, lon in places:
        rt.lat, rt.lon = lat, lon
        rt.lost = False
        assert await fleet._check_boundary(rt, FakeLink()) is False, f"{name} read as outside"

    rt.in_air = False
    rt.lat, rt.lon = site.to_latlon(100.0, 100.0)
    assert await fleet._check_boundary(rt, FakeLink()) is False

    await fleet.shutdown()


def test_the_site_dataset_agrees_with_itself():
    """Our projection reproduces the dataset's own pixel and lat/lon pairs."""
    from app.services import site

    worst = 0.0
    for o in site.OBJECTS[::250]:
        lat, lon = site.to_latlon(*o["px"])
        worst = max(worst, site.metres_between(lat, lon, o["lat"], o["lon"]))
    # the file rounds lat/lon to 7 decimals (~1 cm)
    assert worst < 0.5, f"projection disagrees with the dataset by {worst:.2f} m"

    for o in site.OBJECTS[::500]:
        px, py = site.to_pixel(o["lat"], o["lon"])
        assert abs(px - o["px"][0]) < 1.0 and abs(py - o["px"][1]) < 1.0


def test_site_boundary_contains_the_airfield_and_its_routes():
    """The operational area encloses the pads and routes and excludes open country."""
    from app.services import site

    assert site.inside_boundary(site.HOME_LAT, site.HOME_LON)
    for p in site.LAUNCH_PADS:
        assert site.inside_boundary(p["lat"], p["lon"]), f"{p['designator']} is outside"

    for px, py in [(50, 50), (7950, 50), (50, 5550), (7950, 5550)]:
        lat, lon = site.to_latlon(px, py)
        assert not site.inside_boundary(lat, lon), f"pixel ({px}, {py}) read as inside"
        assert site.distance_outside_m(lat, lon) > 0

    d = site.describe()
    assert d["boundary"] == [list(p) for p in site.BOUNDARY]
    assert d["home_lat"] == site.HOME_LAT

    # every route has at least two points, all inside the area
    assert d["routes"], "the site defines no patrol routes"
    assert d["default_route"] in d["routes"]
    for key, route in d["routes"].items():
        assert len(route["points"]) >= 2, f"route {key} has too few points"
        for lat, lon in route["points"]:
            assert site.inside_boundary(lat, lon), f"route {key} leaves the operational area"


async def test_a_single_out_of_area_reading_does_not_lose_the_aircraft():
    """A breach shorter than the debounce, or a zeroed position, does not lose the aircraft."""
    from app.dronelink.base import DroneRuntime
    from app.services import site
    from app.services.fleet import BOUNDARY_BREACH_TICKS, FleetService

    fleet = FleetService()
    rt = DroneRuntime(id=0, callsign="Sentinel",
                      home_lat=site.HOME_LAT, home_lon=site.HOME_LON, home_alt=95.0)
    rt.enabled, rt.state, rt.in_air = True, "PATROL", True
    fleet.runtimes[0] = rt

    class FakeLink:
        async def land(self): pass

    outside = site.to_latlon(100.0, 100.0)
    inside = (site.HOME_LAT, site.HOME_LON)

    # a glitch shorter than the debounce, then back inside
    for _ in range(BOUNDARY_BREACH_TICKS - 1):
        rt.lat, rt.lon = outside
        assert await fleet._check_boundary(rt, FakeLink()) is False
    rt.lat, rt.lon = inside
    assert await fleet._check_boundary(rt, FakeLink()) is False
    assert rt.lost is False, "a transient reading lost the aircraft"
    assert rt.outside_ticks == 0, "the counter did not reset on a good reading"

    # no telemetry yet: never judged
    rt.lat, rt.lon = 0.0, 0.0
    for _ in range(BOUNDARY_BREACH_TICKS * 2):
        assert await fleet._check_boundary(rt, FakeLink()) is False
    assert rt.lost is False

    await fleet.shutdown()


async def test_reset_recovers_the_drone_even_if_the_drone_service_is_down():
    """Reset clears `lost` and reports the error when the drone service is unreachable."""
    from app.dronelink.base import DroneRuntime
    from app.services.fleet import FleetService, airborne

    fleet = FleetService()
    rt = DroneRuntime(id=0, callsign="Sentinel", home_lat=43.9977991, home_lon=25.0154851, home_alt=95.0)
    rt.lost, rt.state, rt.enabled = True, "SIGNAL_LOST", False
    fleet.runtimes[0] = rt

    class FakeUser:
        id, username, role = 1, "admin", "admin"

    class DeadDroneClient:
        async def reset(self, drone_id):
            raise ConnectionError("connection refused")
        async def power(self, drone_id, on):
            raise ConnectionError("connection refused")
        async def aclose(self): pass

    fleet.drone = DeadDroneClient()
    fleet.audit = _noop_audit

    result = await fleet.maintenance_reset(0, FakeUser())

    assert rt.lost is False, "the aircraft is still written off after a reset"
    assert result["ok"] is True, "reset reported failure despite recovering the drone"
    assert result.get("drone_service_error"), "the drone-service failure was not reported"

    await fleet.shutdown()


async def test_flying_into_a_structure_loses_the_aircraft():
    """Inside a footprint and below its height, the aircraft is lost and cannot be powered on."""
    from app.dronelink.base import DroneRuntime
    from app.services import site
    from app.services.fleet import COLLISION_TICKS, FleetService

    fleet = FleetService()
    rt = DroneRuntime(id=0, callsign="Sentinel",
                      home_lat=site.HOME_LAT, home_lon=site.HOME_LON, home_alt=95.0)
    rt.enabled, rt.state, rt.in_air = True, "PATROL", True
    tower = next(o for o in site.OBJECTS if o["type"] == "control_tower")
    rt.lat, rt.lon = tower["lat"], tower["lon"]
    rt.alt = tower["height_m"] - 10          # below the top: a hit
    fleet.runtimes[0] = rt
    fleet.audit = _noop_audit

    class FakeLink:
        async def land(self): pass

    for _ in range(COLLISION_TICKS - 1):
        assert await fleet._check_collision(rt, FakeLink()) is False, "lost it too early"
    assert await fleet._check_collision(rt, FakeLink()) is True
    assert rt.state == "SIGNAL_LOST"
    assert rt.lost is True
    # cause and struck object are kept on the runtime only
    assert rt.loss_cause == "collision"
    assert rt.loss_object_id == tower["id"]

    rt.enabled = False
    await fleet.power_on(0)
    assert rt.enabled is False, "a lost drone was powered back on"

    await fleet.shutdown()


async def test_flying_above_a_structure_is_safe():
    """Flying above a structure's height is safe."""
    from app.dronelink.base import DroneRuntime
    from app.services import site
    from app.services.fleet import COLLISION_TICKS, FleetService

    fleet = FleetService()
    rt = DroneRuntime(id=0, callsign="Sentinel",
                      home_lat=site.HOME_LAT, home_lon=site.HOME_LON, home_alt=95.0)
    rt.enabled, rt.state, rt.in_air = True, "PATROL", True
    tower = next(o for o in site.OBJECTS if o["type"] == "control_tower")
    rt.lat, rt.lon = tower["lat"], tower["lon"]
    rt.alt = tower["height_m"] + 15          # over the top
    fleet.runtimes[0] = rt

    class FakeLink:
        async def land(self): pass

    for _ in range(COLLISION_TICKS * 2):
        assert await fleet._check_collision(rt, FakeLink()) is False
    assert rt.lost is False

    await fleet.shutdown()


def test_every_predefined_route_clears_the_structures_at_patrol_altitude():
    """Every route clears structures and stays in the area, sampled along each leg."""
    from app.services import site

    PATROL_ALT = 60.0
    for key, route in site.PATROL_ROUTES.items():
        pts = route["points"]
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            steps = max(2, int(site.metres_between(*a, *b) / 25))
            for k in range(steps + 1):
                t = k / steps
                lat = a[0] + (b[0] - a[0]) * t
                lon = a[1] + (b[1] - a[1]) * t
                hit = site.obstacle_at(lat, lon, PATROL_ALT)
                assert hit is None, (
                    f"route {key} leg {i} passes through {hit['id']} "
                    f"({hit['type']}, {hit['height_m']} m) at {PATROL_ALT} m"
                )
                assert site.inside_boundary(lat, lon), f"route {key} leg {i} leaves the area"


def test_the_drone_can_only_launch_from_a_pad():
    """Launching is restricted to helipads, and home is on one."""
    from app.services import site

    assert site.LAUNCH_PADS, "the dataset defines no launch pads"
    assert site.in_launch_area(site.HOME_LAT, site.HOME_LON) is not None

    for p in site.LAUNCH_PADS:
        assert p.get("designator"), f"{p['id']} has no designator"
        found = site.in_launch_area(p["lat"], p["lon"])
        assert found is not None and found["id"] == p["id"]

    assert {"HP-1", "HP-2"} <= set(site.PAD_BY_DESIGNATOR)

    # a runway and open country are refused
    runway = max((o for o in site.OBJECTS if o["type"] == "runway"),
                 key=lambda o: o["length_m"])
    assert site.in_launch_area(runway["lat"], runway["lon"]) is None
    assert site.in_launch_area(*site.to_latlon(100.0, 100.0)) is None


def test_served_object_specs_match_the_collision_detector():
    """The inventory lookup agrees with the collision detector."""
    from app.services import site

    d = site.describe()
    assert d["total_objects"] == len(site.OBJECTS)
    assert d["object_types"], "no type summary served"
    assert d["home_lat"] == site.HOME_LAT

    # sample structures: each is hit below its own height
    checked = 0
    for o in site.OBJECTS:
        if o["type"] in site.NON_COLLIDABLE_TYPES:
            continue
        if o["height_m"] < 2.0 or o.get("footprint_latlon"):
            continue  # concave shapes have centres outside themselves
        checked += 1
        if checked % 97:
            continue
        below = site.obstacle_at(o["lat"], o["lon"], o["height_m"] - 0.5)
        assert below is not None, f"{o['id']} is listed where nothing can be hit"
        found = [h["id"] for h in site.objects_at(o["lat"], o["lon"])]
        assert o["id"] in found, f"{o['id']} not returned by objects_at"

    assert checked > 100, "sample was too small to mean anything"

    # served objects carry a grid reference
    page = site.query_objects(types=["control_tower"], limit=1)
    assert page["total"] == 1
    assert page["objects"][0]["grid_ref"]


def test_the_inventory_can_be_searched_and_filtered():
    """Inventory filters narrow the dataset."""
    from app.services import site

    everything = site.query_objects(limit=1)
    assert everything["total"] == len(site.OBJECTS)

    assert site.query_objects(q="passenger terminal", limit=5)["total"] >= 1
    assert site.query_objects(q="A320", limit=5)["total"] >= 1

    with_scenery = site.query_objects(include_scenery=True, limit=1)["total"]
    without = site.query_objects(include_scenery=False, limit=1)["total"]
    assert without < with_scenery
    for t in site.SCENERY_TYPES:
        assert site.query_objects(types=[t], include_scenery=False, limit=1)["total"] == 0

    tall = site.query_objects(min_height=40, limit=50)
    assert tall["total"] >= 1
    assert all(o["height_m"] >= 40 for o in tall["objects"])

    tower = next(o for o in site.OBJECTS if o["type"] == "control_tower")
    d = 0.002
    box = site.query_objects(
        bounds=(tower["lat"] - d, tower["lon"] - d, tower["lat"] + d, tower["lon"] + d),
        limit=500,
    )
    assert tower["id"] in [o["id"] for o in box["objects"]]
    assert box["total"] < len(site.OBJECTS)

    first = site.query_objects(sort="id", offset=0, limit=10)["objects"]
    second = site.query_objects(sort="id", offset=10, limit=10)["objects"]
    assert len({o["id"] for o in first} & {o["id"] for o in second}) == 0

    assert site.object_by_id(tower["id"])["type"] == "control_tower"
    assert site.object_by_id("NOPE-0001") is None


async def test_altitude_command_changes_height_without_losing_the_patrol():
    """An ALTITUDE command keeps the patrol route and index and reaches the aircraft."""
    from app.dronelink.base import DroneRuntime
    from app.models.user import User
    from app.services import site
    from app.services.fleet import FleetService, airborne

    fleet = FleetService()
    rt = DroneRuntime(id=0, callsign="Sentinel", home_lat=43.9977991, home_lon=25.0154851, home_alt=95.0)
    rt.enabled, rt.state, rt.in_air, rt.alt = True, "PATROL", True, 40.0
    fleet.runtimes[0] = rt

    issued: list[tuple] = []

    class FakeLink:
        async def goto_location(self, lat, lon, alt, yaw):
            issued.append((lat, lon, alt))
        async def set_velocity_ned(self, *a): pass
        async def hold(self): pass

    fleet.links[0] = FakeLink()
    admin = User(id=1, username="admin", role=Role.admin, hashed_password="x", is_active=True)

    route = site.PATROL_ROUTES[site.DEFAULT_ROUTE]["points"]
    rt.patrol_points = list(route)
    rt.patrol_index = 3
    rt.target_alt = 40.0

    ok, _ = await fleet.apply_command(0, "ALTITUDE", {"target_alt": 90.0}, admin)
    assert ok
    assert rt.target_alt == 90.0
    assert rt.state == "PATROL"
    assert rt.patrol_index == 3
    assert len(rt.patrol_points) == len(route)
    assert issued, "no movement was commanded at the new altitude"
    assert abs(issued[-1][2] - ((rt.abs_alt - rt.alt) + 90.0)) < 0.01

    # from HOVER, GOTO the current position (hover would cancel the climb)
    rt.state = "HOVER"
    ok, _ = await fleet.apply_command(0, "ALTITUDE", {"target_alt": 120.0}, admin)
    assert ok
    assert rt.req_state == "GOTO", "a climb from HOVER would be cancelled by the hover setpoint"
    assert rt.target_lat == rt.lat and rt.target_lon == rt.lon

    ok, msg = await fleet.apply_command(0, "ALTITUDE", {}, admin)
    assert not ok and "altitude" in msg


async def test_launching_from_a_pad_does_not_lose_the_aircraft():
    """Climbing off either pad (a helicopter is parked on HP-1) is not a collision."""
    from app.dronelink.base import DroneRuntime
    from app.services import site
    from app.services.fleet import COLLISION_TICKS, FleetService

    class FakeLink:
        async def land(self): pass

    for p in site.LAUNCH_PADS:
        fleet = FleetService()
        rt = DroneRuntime(id=0, callsign="Sentinel",
                          home_lat=p["lat"], home_lon=p["lon"], home_alt=95.0)
        rt.enabled, rt.state, rt.in_air = True, "TAKEOFF", True
        rt.lat, rt.lon = p["lat"], p["lon"]
        fleet.runtimes[0] = rt
        fleet.audit = _noop_audit

        for alt in [0.0, 0.5, 1.0, 2.0, 3.0, 3.5, 4.0, 5.0, 8.0, 15.0, 30.0, 60.0]:
            rt.alt = alt
            for _ in range(COLLISION_TICKS + 1):
                lost = await fleet._check_collision(rt, FakeLink())
                assert lost is False, (
                    f"lost the aircraft at {alt} m climbing off {p['designator']}"
                )
        assert rt.lost is False
        await fleet.shutdown()


def test_the_pad_exemption_does_not_make_the_site_safe():
    """The pad exemption is bounded by pad radius and clearance height."""
    from app.services import site

    # tall enough to clear the helicopter on HP-1
    helicopter = next(o for o in site.OBJECTS if o["type"] == "helicopter")
    assert site.PAD_CLEARANCE_M > helicopter["height_m"]
    # but not so tall that it hides real structures
    assert site.PAD_CLEARANCE_M < 15.0

    # above the clearance a pad is ordinary ground
    for p in site.LAUNCH_PADS:
        assert site.on_a_pad(p["lat"], p["lon"], 0.0) is True
        assert site.on_a_pad(p["lat"], p["lon"], site.PAD_CLEARANCE_M + 0.1) is False

    # away from a pad nothing is exempt
    tower = next(o for o in site.OBJECTS if o["type"] == "control_tower")
    assert site.on_a_pad(tower["lat"], tower["lon"], 0.0) is False
    assert site.obstacle_at(tower["lat"], tower["lon"], 20.0) is not None

    # the tallest structures are still hit below their height
    for o in sorted(site.OBJECTS, key=lambda x: -x["height_m"])[:5]:
        if o.get("footprint_latlon"):
            continue
        assert site.obstacle_at(o["lat"], o["lon"], o["height_m"] - 1.0) is not None


async def test_telemetry_carries_the_mission_for_everyone():
    """Telemetry broadcasts the current target and patrol route to every user."""
    import json

    from app.dronelink.base import DroneRuntime
    from app.services import site
    from app.services.fleet import FleetService, airborne

    fleet = FleetService()
    rt = DroneRuntime(id=0, callsign="Sentinel",
                      home_lat=site.HOME_LAT, home_lon=site.HOME_LON, home_alt=95.0)
    fleet.runtimes[0] = rt

    rt.enabled, rt.state = True, "HOVER"
    payload = json.loads(fleet._telemetry_payload())["drones"]["0"]
    assert payload["target"] is None
    assert payload["patrol"] is None

    route = site.PATROL_ROUTES[site.DEFAULT_ROUTE]["points"]
    rt.state = "GOTO"
    rt.target_lat, rt.target_lon, rt.target_alt = route[0][0], route[0][1], 80.0
    payload = json.loads(fleet._telemetry_payload())["drones"]["0"]
    assert payload["target"] == {"lat": route[0][0], "lon": route[0][1], "alt": 80.0}

    # patrol: whole route and current leg
    rt.state = "PATROL"
    rt.patrol_points = list(route)
    rt.patrol_index = 2
    payload = json.loads(fleet._telemetry_payload())["drones"]["0"]
    assert payload["patrol"]["index"] == 2
    assert payload["patrol"]["points"] == [[lat, lon] for lat, lon in route]
    assert json.loads(json.dumps(payload))["patrol"]["points"][0] == list(route[0])

    await fleet.shutdown()


def test_searching_near_a_position_finds_what_was_there():
    """Proximity search returns objects nearest first, with distances to the footprint."""
    from app.services import site

    tower = next(o for o in site.OBJECTS if o["type"] == "control_tower")

    # a structure's own position returns it at distance zero
    r = site.query_objects(near=(tower["lat"], tower["lon"]), radius_m=50, limit=20)
    assert r["objects"], "nothing found at a known structure"
    assert r["objects"][0]["id"] == tower["id"]
    assert r["objects"][0]["distance_m"] == 0.0

    distances = [o["distance_m"] for o in r["objects"]]
    assert distances == sorted(distances), "results are not nearest-first"
    assert all(d <= 50 for d in distances)

    # Open country has only scenery (land use covers the whole map).
    corner = site.to_latlon(100.0, 100.0)
    bare = site.query_objects(near=corner, radius_m=5, include_scenery=False, limit=5)
    assert bare["total"] == 0, f"found structures in open farmland: {bare['objects']}"
    land = site.query_objects(near=corner, radius_m=5, limit=5)
    assert land["total"] >= 1
    assert land["objects"][0]["distance_m"] == 0.0

    # distance is to the footprint, not the centre
    terminal = next(
        o for o in site.OBJECTS
        if o["type"] == "building" and o.get("use") == "passenger terminal"
    )
    edge_lat, edge_lon = site.offset_latlon(
        terminal["lat"], terminal["lon"], terminal["width_m"] / 2 + 10, 0.0
    )
    near_edge = site.query_objects(near=(edge_lat, edge_lon), radius_m=40, limit=50)
    found = {o["id"]: o["distance_m"] for o in near_edge["objects"]}
    assert terminal["id"] in found, "the terminal was not found from just outside it"
    assert found[terminal["id"]] < 40, (
        f"measured {found[terminal['id']]:.0f} m to a building 10 m away "
        "-- distance is being taken to the centre"
    )

    tall = site.query_objects(
        near=(tower["lat"], tower["lon"]), radius_m=500, min_height=10, limit=50
    )
    assert all(o["height_m"] >= 10 for o in tall["objects"])


async def test_takeoff_reaches_the_altitude_it_was_given():
    """Takeoff levels off within an absolute tolerance of the target, at any height."""
    from app.dronelink.base import DroneRuntime
    from app.services import site
    from app.services.fleet import TAKEOFF_TOLERANCE_M, FleetService

    fleet = FleetService()
    rt = DroneRuntime(id=0, callsign="Sentinel",
                      home_lat=site.HOME_LAT, home_lon=site.HOME_LON, home_alt=95.0)
    rt.enabled, rt.in_air = True, True
    rt.lat, rt.lon = site.HOME_LAT, site.HOME_LON
    fleet.runtimes[0] = rt

    commanded: list[float] = []

    class FakeLink:
        async def set_velocity_ned(self, n, e, d, yaw): commanded.append(d)
        async def land(self): pass
        async def hold(self): pass
        async def goto_location(self, *a): pass

    link = FakeLink()

    for target in (20.0, 60.0, 120.0):
        rt.state = rt.req_state = "TAKEOFF"
        rt.target_alt = target
        rt.alt = 0.0
        commanded.clear()
        for _ in range(4000):
            await fleet._tick(rt, link)
            if rt.req_state == "HOVER":
                break
            rt.alt += -commanded[-1] * 0.1
        assert rt.req_state == "HOVER", f"never levelled off climbing to {target} m"
        shortfall = target - rt.alt
        assert abs(shortfall) <= TAKEOFF_TOLERANCE_M + 0.5, (
            f"asked for {target} m, levelled at {rt.alt:.1f} m "
            f"({shortfall:+.1f} m out)"
        )

    await fleet.shutdown()


async def test_seeding_makes_configuration_authoritative():
    """Seeding re-asserts configured passwords, roles and active flags on an existing database."""
    from sqlalchemy import select

    from app.config import settings
    from app.core.rbac import Role
    from app.core.security import hash_password, verify_password
    from app.db.base import AsyncSessionLocal, init_db
    from app.models.user import User
    from app.seed import seed

    await init_db()

    await seed()
    async with AsyncSessionLocal() as s:
        admin = (await s.execute(
            select(User).where(User.username == settings.admin_username)
        )).scalar_one()
        assert verify_password(settings.admin_password, admin.hashed_password)

    # simulate a redeploy: old password, operator disabled and demoted
    async with AsyncSessionLocal() as s:
        admin = (await s.execute(
            select(User).where(User.username == settings.admin_username)
        )).scalar_one()
        admin.hashed_password = hash_password("the-password-from-last-time")
        op = (await s.execute(
            select(User).where(User.username == settings.operator_username)
        )).scalar_one()
        op.is_active = False
        op.role = Role.observer
        await s.commit()

    await seed()
    async with AsyncSessionLocal() as s:
        admin = (await s.execute(
            select(User).where(User.username == settings.admin_username)
        )).scalar_one()
        assert verify_password(settings.admin_password, admin.hashed_password), (
            "the configured admin password did not take effect on a redeploy"
        )
        assert not verify_password("the-password-from-last-time", admin.hashed_password)
        assert admin.role == Role.admin

        op = (await s.execute(
            select(User).where(User.username == settings.operator_username)
        )).scalar_one()
        assert op.is_active is True, "a disabled account was not restored"
        assert op.role == Role.operator, "a demoted account was not restored"
        assert verify_password(settings.operator_password, op.hashed_password), (
            "the configured operator password did not take effect"
        )
