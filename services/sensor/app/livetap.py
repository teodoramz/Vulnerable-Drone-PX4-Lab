"""Live per-flow packet counters sniffed from the capture interfaces (AF_PACKET).

Suricata logs a flow only when it ends, so continuous MAVLink telemetry never
appears there. Also keeps a short ring of recent packets with the MAVLink
message id decoded from a fixed header offset. Not a detector: Suricata decides
what is an attack. Linux only; degrades to an empty view elsewhere.
"""
from __future__ import annotations

import asyncio
import logging
import socket
import struct
from collections import deque
from datetime import datetime, timezone
import time
from dataclasses import dataclass, field

logger = logging.getLogger("sensor.livetap")

ETH_P_ALL = 0x0003
ETH_HDR = 14
PROTO_NAMES = {1: "ICMP", 6: "TCP", 17: "UDP"}

# MAVLink framing; the id is read at a fixed offset so partial frames are tolerated.
MAVLINK_V1 = 0xFE
MAVLINK_V2 = 0xFD

# Message ids worth naming; the rest show as numbers.
MAVLINK_MSG_NAMES = {
    0: "HEARTBEAT", 1: "SYS_STATUS", 24: "GPS_RAW_INT", 30: "ATTITUDE",
    33: "GLOBAL_POSITION_INT", 36: "SERVO_OUTPUT_RAW", 39: "MISSION_ITEM",
    40: "MISSION_REQUEST", 42: "MISSION_CURRENT", 43: "MISSION_REQUEST_LIST",
    44: "MISSION_COUNT", 45: "MISSION_CLEAR_ALL", 47: "MISSION_ACK",
    66: "REQUEST_DATA_STREAM", 73: "MISSION_ITEM_INT", 74: "VFR_HUD",
    76: "COMMAND_LONG", 77: "COMMAND_ACK", 11: "SET_MODE",
    20: "PARAM_REQUEST_READ", 21: "PARAM_REQUEST_LIST", 22: "PARAM_VALUE",
    23: "PARAM_SET", 84: "SET_POSITION_TARGET_LOCAL_NED",
    86: "SET_POSITION_TARGET_GLOBAL_INT", 87: "POSITION_TARGET_GLOBAL_INT",
    105: "HIGHRES_IMU", 111: "TIMESYNC", 140: "ACTUATOR_CONTROL_TARGET",
    141: "ALTITUDE", 230: "ESTIMATOR_STATUS", 231: "WIND_COV",
    232: "GPS_INPUT", 241: "VIBRATION", 242: "HOME_POSITION",
    245: "EXTENDED_SYS_STATE", 253: "STATUSTEXT", 259: "CAMERA_INFORMATION",
    269: "VIDEO_STREAM_INFORMATION", 340: "UTM_GLOBAL_POSITION",
}

# Commands inside COMMAND_LONG that matter enough to name.
MAV_CMD_NAMES = {
    400: "COMPONENT_ARM_DISARM", 176: "DO_SET_MODE", 20: "NAV_RETURN_TO_LAUNCH",
    21: "NAV_LAND", 22: "NAV_TAKEOFF", 192: "DO_REPOSITION",
    246: "PREFLIGHT_REBOOT_SHUTDOWN", 185: "DO_FLIGHTTERMINATION",
}


def decode_mavlink(payload: bytes) -> dict | None:
    """Message id and name from a UDP payload, or None if it is not MAVLink."""
    if len(payload) < 8:
        return None
    magic = payload[0]
    if magic == MAVLINK_V2:
        if len(payload) < 12:
            return None
        msg_id = payload[7] | (payload[8] << 8) | (payload[9] << 16)
        seq, sysid, compid = payload[4], payload[5], payload[6]
        body = payload[10:]
    elif magic == MAVLINK_V1:
        msg_id = payload[5]
        seq, sysid, compid = payload[2], payload[3], payload[4]
        body = payload[6:]
    else:
        return None

    out = {
        "version": 2 if magic == MAVLINK_V2 else 1,
        "msg_id": msg_id,
        "msg": MAVLINK_MSG_NAMES.get(msg_id, f"#{msg_id}"),
        "seq": seq,
        "sysid": sysid,
        "compid": compid,
    }
    # COMMAND_LONG: command uint16 follows seven floats.
    if msg_id == 76 and len(body) >= 30:
        try:
            command = struct.unpack("<H", body[28:30])[0]
            out["command"] = command
            out["command_name"] = MAV_CMD_NAMES.get(command, f"CMD#{command}")
        except struct.error:
            pass
    return out


@dataclass
class PacketRecord:
    """One packet, as the console shows it."""
    ts: float
    iface: str
    src_ip: str
    src_port: int | None
    dest_ip: str
    dest_port: int | None
    proto: str
    length: int
    mavlink: dict | None
    head: bytes

    def as_dict(self) -> dict:
        return {
            "ts": datetime.fromtimestamp(self.ts, tz=timezone.utc).isoformat(),
            "iface": self.iface,
            "src_ip": self.src_ip,
            "src_port": self.src_port,
            "dest_ip": self.dest_ip,
            "dest_port": self.dest_port,
            "proto": self.proto,
            "length": self.length,
            "mavlink": self.mavlink,
            "hex": self.head.hex(),
            "ascii": "".join(chr(b) if 32 <= b < 127 else "." for b in self.head),
        }


@dataclass
class LiveFlow:
    src_ip: str
    src_port: int | None
    dest_ip: str
    dest_port: int | None
    proto: str
    iface: str
    packets: int = 0
    bytes: int = 0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    def as_dict(self, now: float) -> dict:
        return {
            "src_ip": self.src_ip,
            "src_port": self.src_port,
            "dest_ip": self.dest_ip,
            "dest_port": self.dest_port,
            "proto": self.proto,
            "iface": self.iface,
            "packets": self.packets,
            "bytes": self.bytes,
            "age_s": round(now - self.first_seen, 1),
            "idle_s": round(now - self.last_seen, 1),
            "pps": round(self.packets / max(now - self.first_seen, 1.0), 1),
        }


class LiveTap:
    """Aggregates packets per flow key over a rolling window."""

    def __init__(self, ifaces: list[str], window_s: float = 60.0, max_flows: int = 2000,
                 max_packets: int = 400, head_bytes: int = 64):
        self.ifaces = ifaces
        self.window_s = window_s
        self.max_flows = max_flows
        self.flows: dict[tuple, LiveFlow] = {}
        self.total_packets = 0
        self.total_bytes = 0
        self.available = True
        # Bounded: a live view, not a capture.
        self.packets: deque[PacketRecord] = deque(maxlen=max_packets)
        self.head_bytes = head_bytes
        # Running totals per protocol and per service port.
        self.by_proto: dict[str, dict[str, int]] = {}
        self.by_port: dict[tuple[str, int], dict[str, int]] = {}
        self._tasks: list[asyncio.Task] = []

    # ── lifecycle ────────────────────────────────────────
    async def start(self) -> None:
        for iface in self.ifaces:
            try:
                sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
                sock.bind((iface, 0))
                sock.setblocking(False)
            except (AttributeError, OSError) as exc:
                # AF_PACKET is Linux-only, and binding needs CAP_NET_RAW.
                logger.warning("live tap unavailable on %s: %s", iface, exc)
                self.available = False
                continue
            self._tasks.append(asyncio.create_task(self._reader(sock, iface)))
        self._tasks.append(asyncio.create_task(self._expire_loop()))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()

    # ── capture ──────────────────────────────────────────
    async def _reader(self, sock: socket.socket, iface: str) -> None:
        loop = asyncio.get_running_loop()
        try:
            while True:
                try:
                    frame = await loop.sock_recv(sock, 65535)
                except (BlockingIOError, InterruptedError):
                    continue
                self._ingest(frame, iface)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            # A broken tap must never take the alert path down with it.
            logger.warning("live tap on %s stopped: %s", iface, exc)
        finally:
            sock.close()

    def _ingest(self, frame: bytes, iface: str) -> None:
        if len(frame) < ETH_HDR + 20:
            return
        ethertype = struct.unpack("!H", frame[12:14])[0]
        if ethertype != 0x0800:  # IPv4 only; the lab has no IPv6
            return

        ip = frame[ETH_HDR:]
        ihl = (ip[0] & 0x0F) * 4
        if ihl < 20 or len(ip) < ihl:
            return
        proto_num = ip[9]
        src = socket.inet_ntoa(ip[12:16])
        dst = socket.inet_ntoa(ip[16:20])

        sport = dport = None
        if proto_num in (6, 17) and len(ip) >= ihl + 4:
            sport, dport = struct.unpack("!HH", ip[ihl:ihl + 4])

        key = (src, sport, dst, dport, proto_num, iface)
        now = time.time()
        flow = self.flows.get(key)
        if flow is None:
            if len(self.flows) >= self.max_flows:
                # Drop the stalest rather than grow without bound.
                oldest = min(self.flows, key=lambda k: self.flows[k].last_seen)
                self.flows.pop(oldest, None)
            flow = LiveFlow(
                src_ip=src, src_port=sport, dest_ip=dst, dest_port=dport,
                proto=PROTO_NAMES.get(proto_num, str(proto_num)), iface=iface,
                first_seen=now,
            )
            self.flows[key] = flow

        flow.packets += 1
        flow.bytes += len(frame)
        flow.last_seen = now
        self.total_packets += 1
        self.total_bytes += len(frame)

        # Protocol and port rollups.
        proto_name = flow.proto
        pstat = self.by_proto.setdefault(proto_name, {"packets": 0, "bytes": 0})
        pstat["packets"] += 1
        pstat["bytes"] += len(frame)
        # Lower port is the service side in this lab.
        if sport is not None and dport is not None:
            service = min(sport, dport)
            qstat = self.by_port.setdefault((proto_name, service), {"packets": 0, "bytes": 0})
            qstat["packets"] += 1
            qstat["bytes"] += len(frame)

        payload = b""
        if proto_num == 17 and len(ip) >= ihl + 8:
            payload = ip[ihl + 8:]
        elif proto_num == 6 and len(ip) >= ihl + 20:
            doff = ((ip[ihl + 12] >> 4) & 0x0F) * 4
            if doff >= 20:
                payload = ip[ihl + doff:]

        self.packets.append(PacketRecord(
            ts=now, iface=iface, src_ip=src, src_port=sport, dest_ip=dst,
            dest_port=dport, proto=proto_name, length=len(frame),
            mavlink=decode_mavlink(payload) if payload else None,
            head=bytes(payload[: self.head_bytes]) if payload else b"",
        ))

    async def _expire_loop(self) -> None:
        while True:
            await asyncio.sleep(5)
            cutoff = time.time() - self.window_s
            for key in [k for k, f in self.flows.items() if f.last_seen < cutoff]:
                self.flows.pop(key, None)

    # ── read ─────────────────────────────────────────────
    def snapshot(self, limit: int = 200) -> dict:
        now = time.time()
        rows = sorted(self.flows.values(), key=lambda f: f.last_seen, reverse=True)[:limit]
        return {
            "available": self.available,
            "window_s": self.window_s,
            "ifaces": self.ifaces,
            "total_packets": self.total_packets,
            "total_bytes": self.total_bytes,
            "flows": [f.as_dict(now) for f in rows],
        }

    def recent_packets(self, limit: int = 200, mavlink_only: bool = False) -> dict:
        """The most recent packets, newest first."""
        items = list(self.packets)
        if mavlink_only:
            items = [p for p in items if p.mavlink]
        items.reverse()
        return {
            "available": self.available,
            "captured": len(self.packets),
            "capacity": self.packets.maxlen,
            "head_bytes": self.head_bytes,
            "packets": [p.as_dict() for p in items[:limit]],
        }

    def breakdown(self) -> dict:
        """Totals by protocol and by service port."""
        def rows(d: dict, key) -> list[dict]:
            out = [{**key(k), **v} for k, v in d.items()]
            out.sort(key=lambda r: -r["bytes"])
            return out

        mav = sum(1 for p in self.packets if p.mavlink)
        names: dict[str, int] = {}
        for p in self.packets:
            if p.mavlink:
                names[p.mavlink["msg"]] = names.get(p.mavlink["msg"], 0) + 1
        return {
            "available": self.available,
            "window_s": self.window_s,
            "total_packets": self.total_packets,
            "total_bytes": self.total_bytes,
            "by_proto": rows(self.by_proto, lambda k: {"proto": k}),
            "by_port": rows(self.by_port, lambda k: {"proto": k[0], "port": k[1]}),
            "mavlink_in_ring": mav,
            "ring_size": len(self.packets),
            "mavlink_messages": sorted(
                ({"msg": k, "packets": v} for k, v in names.items()),
                key=lambda r: -r["packets"],
            ),
        }
