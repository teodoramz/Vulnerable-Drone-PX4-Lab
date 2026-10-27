"""MAVLink 2 UDP surface (port 14550) in front of the mock simulator.

DELIBERATE VULNERABILITY: behaves like PX4 SITL's GCS link. It broadcasts
telemetry to every peer that has sent it traffic and acts on unauthenticated
flight commands. Shares MockSimulator/SimDrone state with the /ws path.

Simplifications: no EKF (GPS_INPUT overwrites ground-truth position), no
failsafe or geofence logic, a stub parameter table (app/mavlink/params.py),
and uploaded missions are flown as plain lat/lon/alt gotos. Use
DRONE_BACKEND=px4 for protocol-accurate parameter and geofence attacks.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import time

from pymavlink.dialects.v20 import common as mavlink2

from app.mavlink.params import DEFAULT_PARAMS
from app.mock.simulator import MockSimulator, SimDrone

logger = logging.getLogger("drone.mavlink")

GCS_PORT = 14550
MAV_COMPONENT_ID = mavlink2.MAV_COMP_ID_AUTOPILOT1

HEARTBEAT_HZ = 1.0
GLOBAL_POSITION_HZ = 10.0
GPS_RAW_HZ = 5.0
SYS_STATUS_HZ = 2.0
ATTITUDE_HZ = 10.0
EXTENDED_SYS_STATE_HZ = 2.0

# Approximate PX4 custom_mode (uint32): main_mode in byte 2, sub_mode in byte 3.
# Cosmetic only (HEARTBEAT/SET_MODE).
_PX4_MAIN_MANUAL = 1
_PX4_MAIN_POSCTL = 3
_PX4_MAIN_AUTO = 4
_PX4_MAIN_OFFBOARD = 6
_PX4_SUB_AUTO_LOITER = 3
_PX4_SUB_AUTO_MISSION = 4
_PX4_SUB_AUTO_RTL = 5
_PX4_SUB_AUTO_LAND = 6

_MODE_TO_MAIN_SUB: dict[str, tuple[int, int]] = {
    "IDLE": (_PX4_MAIN_POSCTL, 0),
    "VELOCITY": (_PX4_MAIN_OFFBOARD, 0),
    "GOTO": (_PX4_MAIN_OFFBOARD, 0),
    "LAND": (_PX4_MAIN_AUTO, _PX4_SUB_AUTO_LAND),
    "RTL": (_PX4_MAIN_AUTO, _PX4_SUB_AUTO_RTL),
    "MISSION": (_PX4_MAIN_AUTO, _PX4_SUB_AUTO_MISSION),
    "FALLING": (_PX4_MAIN_MANUAL, 0),
}


def _custom_mode(mode: str) -> int:
    main, sub = _MODE_TO_MAIN_SUB.get(mode, (_PX4_MAIN_POSCTL, 0))
    return (sub << 24) | (main << 16)


class _BroadcastEndpoint:
    """File-like sink for MAVLink.send(); fans bytes out to every known peer."""

    def __init__(self, owner: "MavlinkTransport") -> None:
        self._owner = owner

    def write(self, buf: bytes) -> None:
        self._owner._broadcast(buf)


class MavlinkTransport:
    """Owns the UDP 14550 socket, emits telemetry, and applies inbound commands."""

    def __init__(self, simulator: MockSimulator, host: str = "0.0.0.0", port: int = GCS_PORT):
        self.sim = simulator
        self.host = host
        self.port = port

        self._socket: asyncio.DatagramTransport | None = None
        self.peers: set[tuple[str, int]] = set()

        self._tx: dict[int, mavlink2.MAVLink] = {}
        self._rx = mavlink2.MAVLink(None, srcSystem=255, srcComponent=190)
        self._rx.robust_parsing = True

        self._params: dict[int, dict[str, float]] = {}
        self._mission_uploads: dict[int, dict] = {}

        self._start_time = time.monotonic()
        self._tasks: list[asyncio.Task] = []

    # ── lifecycle ────────────────────────────────────────
    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._socket, _ = await loop.create_datagram_endpoint(
            lambda: _MavlinkServerProtocol(self),
            local_addr=(self.host, self.port),
        )
        logger.info("mavlink: listening on %s:%s (udp)", self.host, self.port)
        self._tasks = [
            asyncio.create_task(self._emit_loop(self._emit_heartbeat, HEARTBEAT_HZ)),
            asyncio.create_task(self._emit_loop(self._emit_global_position, GLOBAL_POSITION_HZ)),
            asyncio.create_task(self._emit_loop(self._emit_gps_raw, GPS_RAW_HZ)),
            asyncio.create_task(self._emit_loop(self._emit_sys_status, SYS_STATUS_HZ)),
            asyncio.create_task(self._emit_loop(self._emit_attitude, ATTITUDE_HZ)),
            asyncio.create_task(self._emit_loop(self._emit_extended_sys_state, EXTENDED_SYS_STATE_HZ)),
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks = []
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def _boot_ms(self) -> int:
        return int((time.monotonic() - self._start_time) * 1000) & 0xFFFFFFFF

    def _tx_for(self, drone_id: int) -> mavlink2.MAVLink:
        mav = self._tx.get(drone_id)
        if mav is None:
            mav = mavlink2.MAVLink(_BroadcastEndpoint(self), srcSystem=drone_id + 1, srcComponent=MAV_COMPONENT_ID)
            mav.robust_parsing = True
            self._tx[drone_id] = mav
        return mav

    def _broadcast(self, buf: bytes) -> None:
        if self._socket is None:
            return
        for peer in list(self.peers):
            self._socket.sendto(buf, peer)

    def _send_to(self, drone_id: int, msg: mavlink2.MAVLink_message, addr: tuple[str, int]) -> None:
        if self._socket is None:
            return
        mav = self._tx_for(drone_id)
        buf = msg.pack(mav)
        mav.seq = (mav.seq + 1) % 256
        self._socket.sendto(buf, addr)

    # ── inbound ──────────────────────────────────────────
    def _on_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        self.peers.add(addr)
        try:
            msgs = self._rx.parse_buffer(bytearray(data))
        except Exception:  # noqa: BLE001 - never let garbage on the wire kill the transport
            logger.debug("mavlink: unparsable datagram from %s", addr, exc_info=True)
            return
        if not msgs:
            return
        for msg in msgs:
            try:
                self._handle_message(msg, addr)
            except Exception:  # noqa: BLE001 - attacker input must not crash the loop
                logger.exception("mavlink: error handling %s from %s", msg.get_type(), addr)

    def _resolve_drone(self, target_system: int) -> SimDrone | None:
        drone = self.sim.drones.get(target_system - 1)
        if drone is not None:
            return drone
        if len(self.sim.drones) == 1:
            return next(iter(self.sim.drones.values()))
        return None

    _DISPATCH_ATTR = {
        "COMMAND_LONG": "_handle_command_long",
        # Same commands as COMMAND_LONG with integer-scaled lat/lon (DO_REPOSITION).
        "COMMAND_INT": "_handle_command_int",
        "SET_MODE": "_handle_set_mode",
        "SET_POSITION_TARGET_GLOBAL_INT": "_handle_set_position_target",
        "MISSION_COUNT": "_handle_mission_count",
        "MISSION_ITEM_INT": "_handle_mission_item_int",
        "GPS_INPUT": "_handle_gps_input",
        "PARAM_SET": "_handle_param_set",
        "PARAM_REQUEST_LIST": "_handle_param_request_list",
        "PARAM_REQUEST_READ": "_handle_param_request_read",
    }

    def _handle_message(self, msg: mavlink2.MAVLink_message, addr: tuple[str, int]) -> None:
        attr = self._DISPATCH_ATTR.get(msg.get_type())
        if attr is None:
            return  # HEARTBEATs from GCS tools and anything else we don't model: ignore
        getattr(self, attr)(msg, addr)

    # ── COMMAND_LONG ─────────────────────────────────────
    def _handle_command_long(self, msg, addr: tuple[str, int]) -> None:
        drone = self._resolve_drone(msg.target_system)
        if drone is None:
            return
        handlers = {
            mavlink2.MAV_CMD_COMPONENT_ARM_DISARM: lambda: self._cmd_arm_disarm(drone, msg.param1, msg.param2),
            mavlink2.MAV_CMD_NAV_TAKEOFF: lambda: self._cmd_takeoff(drone, msg.param7),
            mavlink2.MAV_CMD_NAV_LAND: lambda: self._cmd_land(drone),
            mavlink2.MAV_CMD_NAV_RETURN_TO_LAUNCH: lambda: self._cmd_rtl(drone),
            mavlink2.MAV_CMD_DO_REPOSITION: lambda: self._cmd_reposition(drone, msg.param5, msg.param6, msg.param7),
        }
        handler = handlers.get(msg.command)
        result = handler() if handler is not None else mavlink2.MAV_RESULT_UNSUPPORTED
        ack = self._tx_for(drone.id).command_ack_encode(msg.command, result)
        self._send_to(drone.id, ack, addr)

    def _handle_command_int(self, msg, addr: tuple[str, int]) -> None:
        """COMMAND_INT: as COMMAND_LONG, but x/y are degrees x 1e7."""
        drone = self._resolve_drone(msg.target_system)
        if drone is None:
            return
        handlers = {
            mavlink2.MAV_CMD_COMPONENT_ARM_DISARM:
                lambda: self._cmd_arm_disarm(drone, msg.param1, msg.param2),
            mavlink2.MAV_CMD_NAV_TAKEOFF: lambda: self._cmd_takeoff(drone, msg.z),
            mavlink2.MAV_CMD_NAV_LAND: lambda: self._cmd_land(drone),
            mavlink2.MAV_CMD_NAV_RETURN_TO_LAUNCH: lambda: self._cmd_rtl(drone),
            mavlink2.MAV_CMD_DO_REPOSITION:
                lambda: self._cmd_reposition(drone, msg.x / 1e7, msg.y / 1e7, msg.z),
        }
        handler = handlers.get(msg.command)
        result = handler() if handler is not None else mavlink2.MAV_RESULT_UNSUPPORTED
        ack = self._tx_for(drone.id).command_ack_encode(msg.command, result)
        self._send_to(drone.id, ack, addr)

    def _cmd_arm_disarm(self, drone: SimDrone, param1: float, param2: float) -> int:
        if not drone.enabled:
            return mavlink2.MAV_RESULT_DENIED
        arm = param1 >= 0.5
        force = int(round(param2)) == 21196
        if arm:
            drone.armed = True
            if drone.mode == "FALLING":
                drone.mode = "IDLE"
            return mavlink2.MAV_RESULT_ACCEPTED
        # In-air disarm needs the PX4 force magic (param2 == 21196), which the kill exploit uses.
        if drone.in_air and not force:
            return mavlink2.MAV_RESULT_DENIED
        drone.armed = False
        if drone.in_air:
            drone.mode = "FALLING"  # no motors, no controlled descent: it drops
        else:
            drone.mode = "IDLE"
            drone.vN = drone.vE = drone.vD = 0.0
        return mavlink2.MAV_RESULT_ACCEPTED

    def _cmd_takeoff(self, drone: SimDrone, alt_param: float) -> int:
        if not drone.enabled:
            return mavlink2.MAV_RESULT_DENIED
        drone.armed = True
        drone.target_lat = drone.lat
        drone.target_lon = drone.lon
        drone.target_rel_alt = alt_param if alt_param > 0 else 10.0
        drone.mode = "GOTO"
        return mavlink2.MAV_RESULT_ACCEPTED

    def _cmd_land(self, drone: SimDrone) -> int:
        if not drone.enabled:
            return mavlink2.MAV_RESULT_DENIED
        drone.mode = "LAND"
        return mavlink2.MAV_RESULT_ACCEPTED

    def _cmd_rtl(self, drone: SimDrone) -> int:
        if not drone.enabled or not drone.in_air:
            return mavlink2.MAV_RESULT_DENIED
        drone.target_lat = drone.home_lat
        drone.target_lon = drone.home_lon
        drone.target_rel_alt = drone.rel_alt
        drone.mode = "RTL"
        return mavlink2.MAV_RESULT_ACCEPTED

    def _cmd_reposition(self, drone: SimDrone, lat: float, lon: float, alt: float) -> int:
        if not drone.enabled:
            return mavlink2.MAV_RESULT_DENIED
        if lat == 0.0 and lon == 0.0:
            return mavlink2.MAV_RESULT_DENIED
        drone.armed = True
        drone.target_lat = lat
        drone.target_lon = lon
        drone.target_rel_alt = alt if alt else drone.rel_alt
        drone.mode = "GOTO"
        return mavlink2.MAV_RESULT_ACCEPTED

    # ── SET_MODE ─────────────────────────────────────────
    def _handle_set_mode(self, msg, addr: tuple[str, int]) -> None:
        drone = self._resolve_drone(msg.target_system)
        if drone is None or not drone.enabled:
            return
        if msg.base_mode & mavlink2.MAV_MODE_FLAG_SAFETY_ARMED:
            drone.armed = True
        main_mode = (msg.custom_mode >> 16) & 0xFF
        sub_mode = (msg.custom_mode >> 24) & 0xFF
        if main_mode == _PX4_MAIN_OFFBOARD:
            drone.mode = "VELOCITY"
            drone.vN = drone.vE = drone.vD = 0.0
        elif main_mode == _PX4_MAIN_AUTO:
            if sub_mode == _PX4_SUB_AUTO_RTL:
                self._cmd_rtl(drone)
            elif sub_mode == _PX4_SUB_AUTO_LAND:
                drone.mode = "LAND"
            elif sub_mode == _PX4_SUB_AUTO_MISSION and drone.mission_items:
                drone.mode = "MISSION"
        # SET_MODE has no COMMAND_ACK in the MAVLink spec; we just apply it.

    # ── SET_POSITION_TARGET_GLOBAL_INT ───────────────────
    def _handle_set_position_target(self, msg, addr: tuple[str, int]) -> None:
        drone = self._resolve_drone(msg.target_system)
        if drone is None or not drone.enabled:
            return
        mask = msg.type_mask
        pos_ignored = bool(mask & mavlink2.POSITION_TARGET_TYPEMASK_X_IGNORE)
        vel_ignored = bool(mask & mavlink2.POSITION_TARGET_TYPEMASK_VX_IGNORE)
        if not pos_ignored:
            drone.armed = True
            drone.target_lat = msg.lat_int / 1e7
            drone.target_lon = msg.lon_int / 1e7
            # Altitude is always treated as relative (AMSL vs relative not distinguished).
            drone.target_rel_alt = msg.alt
            drone.mode = "GOTO"
        elif not vel_ignored:
            drone.mode = "VELOCITY"
            drone.vN, drone.vE, drone.vD = msg.vx, msg.vy, msg.vz
            if drone.vD < 0:
                drone.armed = True

    # ── mission upload (MISSION_COUNT / MISSION_ITEM_INT) ─
    def _handle_mission_count(self, msg, addr: tuple[str, int]) -> None:
        drone = self._resolve_drone(msg.target_system)
        if drone is None:
            return
        target_system = msg.target_system or (drone.id + 1)
        target_component = msg.target_component or MAV_COMPONENT_ID
        if msg.count <= 0:
            drone.mission_items = []
            drone.mission_index = 0
            ack = self._tx_for(drone.id).mission_ack_encode(target_system, target_component, mavlink2.MAV_MISSION_ACCEPTED)
            self._send_to(drone.id, ack, addr)
            return
        self._mission_uploads[drone.id] = {
            "addr": addr,
            "count": msg.count,
            "items": {},
            "target_system": target_system,
            "target_component": target_component,
        }
        req = self._tx_for(drone.id).mission_request_int_encode(target_system, target_component, 0)
        self._send_to(drone.id, req, addr)

    def _handle_mission_item_int(self, msg, addr: tuple[str, int]) -> None:
        drone = self._resolve_drone(msg.target_system)
        if drone is None:
            return
        upload = self._mission_uploads.get(drone.id)
        if upload is None:
            return  # unsolicited item outside of an active upload: ignore
        upload["items"][msg.seq] = (msg.x / 1e7, msg.y / 1e7, msg.z)
        next_seq = msg.seq + 1
        if next_seq < upload["count"]:
            req = self._tx_for(drone.id).mission_request_int_encode(
                upload["target_system"], upload["target_component"], next_seq
            )
            self._send_to(drone.id, req, addr)
            return
        items = [upload["items"][i] for i in range(upload["count"]) if i in upload["items"]]
        drone.mission_items = items
        drone.mission_index = 0
        del self._mission_uploads[drone.id]
        ack = self._tx_for(drone.id).mission_ack_encode(
            upload["target_system"], upload["target_component"], mavlink2.MAV_MISSION_ACCEPTED
        )
        self._send_to(drone.id, ack, addr)
        # DELIBERATE VULNERABILITY: an uploaded mission starts flying at once
        # (real PX4 waits for MISSION_START or a mode switch).
        if drone.enabled and items:
            drone.armed = True
            drone.mode = "MISSION"

    # ── maintenance reset ─────────────────────────────────
    def reset_drone(self, drone_id: int) -> dict:
        """Clear tampered params, a pending mission upload and all telemetry peers.

        A power cycle resets the vehicle but not this state. Returns what was cleared.
        """
        params = self._params.pop(drone_id, None)
        changed = (
            sorted(k for k, v in params.items() if DEFAULT_PARAMS.get(k) != v)
            if params
            else []
        )
        pending_mission = self._mission_uploads.pop(drone_id, None)
        dropped_peers = len(self.peers)
        # Legitimate peers re-register on their next datagram.
        self.peers.clear()

        return {
            "params_restored": changed,
            "mission_upload_discarded": pending_mission is not None,
            "peers_dropped": dropped_peers,
        }

    # ── GPS_INPUT (GPS spoofing) ──────────────────────────
    def _handle_gps_input(self, msg, addr: tuple[str, int]) -> None:
        # GPS_INPUT has no target_system, so the fix applies to every enabled drone.
        lat = msg.lat / 1e7
        lon = msg.lon / 1e7
        alt_ignored = bool(msg.ignore_flags & mavlink2.GPS_INPUT_IGNORE_FLAG_ALT)
        for drone in self.sim.drones.values():
            if not drone.enabled:
                continue
            # DELIBERATE VULNERABILITY: no EKF, so the spoofed fix becomes the true position.
            drone.lat = lat
            drone.lon = lon
            if not alt_ignored:
                drone.rel_alt = max(0.0, msg.alt - drone.home_alt)

    # ── PARAM_* (stub table) ──────────────────────────────
    def _table_for(self, drone_id: int) -> dict[str, float]:
        return self._params.setdefault(drone_id, dict(DEFAULT_PARAMS))

    @staticmethod
    def _param_name(raw) -> str:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        return raw.split("\x00", 1)[0]

    def _handle_param_set(self, msg, addr: tuple[str, int]) -> None:
        drone = self._resolve_drone(msg.target_system)
        if drone is None:
            return
        table = self._table_for(drone.id)
        name = self._param_name(msg.param_id)
        if name not in table:
            return  # unknown param: a real vehicle would reject it too
        table[name] = msg.param_value
        names = list(table)
        value = self._tx_for(drone.id).param_value_encode(
            name.encode()[:16], table[name], mavlink2.MAV_PARAM_TYPE_REAL32, len(table), names.index(name)
        )
        self._send_to(drone.id, value, addr)

    def _handle_param_request_list(self, msg, addr: tuple[str, int]) -> None:
        drone = self._resolve_drone(msg.target_system)
        if drone is None:
            return
        table = self._table_for(drone.id)
        names = list(table)
        for idx, name in enumerate(names):
            value = self._tx_for(drone.id).param_value_encode(
                name.encode()[:16], table[name], mavlink2.MAV_PARAM_TYPE_REAL32, len(names), idx
            )
            self._send_to(drone.id, value, addr)

    def _handle_param_request_read(self, msg, addr: tuple[str, int]) -> None:
        drone = self._resolve_drone(msg.target_system)
        if drone is None:
            return
        table = self._table_for(drone.id)
        names = list(table)
        name = self._param_name(msg.param_id) if msg.param_index < 0 else (
            names[msg.param_index] if 0 <= msg.param_index < len(names) else None
        )
        if name is None or name not in table:
            return
        value = self._tx_for(drone.id).param_value_encode(
            name.encode()[:16], table[name], mavlink2.MAV_PARAM_TYPE_REAL32, len(names), names.index(name)
        )
        self._send_to(drone.id, value, addr)

    # ── telemetry emission ───────────────────────────────
    async def _emit_loop(self, emit_fn, hz: float) -> None:
        interval = 1.0 / hz
        try:
            while True:
                for drone in list(self.sim.drones.values()):
                    if drone.enabled:
                        emit_fn(drone)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass

    def _emit_heartbeat(self, drone: SimDrone) -> None:
        base_mode = mavlink2.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
        if drone.armed:
            base_mode |= mavlink2.MAV_MODE_FLAG_SAFETY_ARMED
        if drone.mode in ("VELOCITY", "GOTO", "RTL", "MISSION"):
            base_mode |= mavlink2.MAV_MODE_FLAG_GUIDED_ENABLED
        system_status = mavlink2.MAV_STATE_ACTIVE if drone.armed else mavlink2.MAV_STATE_STANDBY
        msg = self._tx_for(drone.id).heartbeat_encode(
            mavlink2.MAV_TYPE_QUADROTOR,
            mavlink2.MAV_AUTOPILOT_PX4,
            base_mode,
            _custom_mode(drone.mode),
            system_status,
        )
        self._tx_for(drone.id).send(msg)

    def _emit_global_position(self, drone: SimDrone) -> None:
        heading_cdeg = int(round(drone.heading * 100)) % 36000
        msg = self._tx_for(drone.id).global_position_int_encode(
            self._boot_ms(),
            int(round(drone.lat * 1e7)),
            int(round(drone.lon * 1e7)),
            int(round(drone.abs_alt * 1000)),
            int(round(drone.rel_alt * 1000)),
            int(round(max(-32.767, min(32.767, drone.vN)) * 100)),
            int(round(max(-32.767, min(32.767, drone.vE)) * 100)),
            int(round(max(-32.767, min(32.767, drone.vD)) * 100)),
            heading_cdeg,
        )
        self._tx_for(drone.id).send(msg)

    def _emit_gps_raw(self, drone: SimDrone) -> None:
        speed = (drone.vN**2 + drone.vE**2) ** 0.5
        msg = self._tx_for(drone.id).gps_raw_int_encode(
            self._boot_ms() * 1000,
            mavlink2.GPS_FIX_TYPE_3D_FIX,
            int(round(drone.lat * 1e7)),
            int(round(drone.lon * 1e7)),
            int(round(drone.abs_alt * 1000)),
            100,  # eph (stub: 1.0 m)
            100,  # epv (stub: 1.0 m)
            int(round(speed * 100)),
            int(round(drone.heading * 100)) % 36000,
            10,  # satellites_visible (stub)
        )
        self._tx_for(drone.id).send(msg)

    def _emit_sys_status(self, drone: SimDrone) -> None:
        # No power model: fixed healthy battery.
        msg = self._tx_for(drone.id).sys_status_encode(
            0, 0, 0,  # sensor present/enabled/health bitmasks: not modelled
            0,  # load
            12600,  # voltage_battery mV
            -1,  # current_battery: not measured
            100,  # battery_remaining %
            0, 0, 0, 0, 0, 0,
        )
        self._tx_for(drone.id).send(msg)

    def _emit_attitude(self, drone: SimDrone) -> None:
        # Kinematic mock: no roll/pitch model, only yaw (heading) is real.
        msg = self._tx_for(drone.id).attitude_encode(
            self._boot_ms(),
            0.0,
            0.0,
            math.radians(drone.heading),
            0.0,
            0.0,
            0.0,
        )
        self._tx_for(drone.id).send(msg)

    def _emit_extended_sys_state(self, drone: SimDrone) -> None:
        if drone.mode == "LAND" and drone.in_air:
            landed_state = mavlink2.MAV_LANDED_STATE_LANDING
        elif drone.in_air:
            landed_state = mavlink2.MAV_LANDED_STATE_IN_AIR
        else:
            landed_state = mavlink2.MAV_LANDED_STATE_ON_GROUND
        msg = self._tx_for(drone.id).extended_sys_state_encode(
            mavlink2.MAV_VTOL_STATE_UNDEFINED,
            landed_state,
        )
        self._tx_for(drone.id).send(msg)


class _MavlinkServerProtocol(asyncio.DatagramProtocol):
    """Thin asyncio glue: hands raw datagrams to the transport."""

    def __init__(self, owner: MavlinkTransport) -> None:
        self._owner = owner

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self._owner._on_datagram(data, addr)

    def error_received(self, exc: Exception) -> None:
        logger.warning("mavlink: udp error: %s", exc)
