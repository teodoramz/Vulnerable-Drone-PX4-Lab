"""Regenerate mavlink-attacks.pcap, the fixture test_rules_against_pcap replays.

Encodes one frame per attack message in both wire formats, since the ruleset
needs a rule per format and a fixture carrying only one would pass against a
ruleset that is blind to the other. Decoy frames carry every rule's msgid in
their payload, so a rule that reads past the msgid field fires on them.

    python3 services/sensor/tests/fixtures/make_pcap.py
"""
from __future__ import annotations

import inspect
import socket
import struct
import sys
from pathlib import Path

from pymavlink.dialects.v10 import common as v1
from pymavlink.dialects.v20 import common as v2

ATTACKER = "172.18.0.77"
DRONE = "172.18.0.2"
PORT = 14550
KILL_MAGIC = 21196.0
# Message ids the ruleset matches.
RULE_MSGIDS = (11, 23, 44, 45, 73, 75, 76, 86, 113, 232)


class Sink:
    """pymavlink writes packed frames to a file-like object."""

    def __init__(self) -> None:
        self.frames: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.frames.append(data)


def send(mav, name: str, *args) -> None:
    """Call a *_send method, zero-padding the fields v2 added after v1."""
    fn = getattr(mav, name)
    wanted = len(inspect.signature(fn).parameters) - 1  # force_mavlink1 defaults
    fn(*args, *([0] * (wanted - len(args))))


def frames_for(dialect) -> list[bytes]:
    sink = Sink()
    mav = dialect.MAVLink(sink, srcSystem=255, srcComponent=190)
    arm = dialect.MAV_CMD_COMPONENT_ARM_DISARM
    frame = dialect.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT
    send(mav, "command_long_send", 1, 1, arm, 0, 1, 0, 0, 0, 0, 0, 0)
    send(mav, "command_long_send", 1, 1, arm, 0, 0, KILL_MAGIC, 0, 0, 0, 0, 0)
    send(mav, "set_mode_send", 1, dialect.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 4)
    send(mav, "command_int_send", 1, 1, frame, dialect.MAV_CMD_DO_REPOSITION,
         0, 0, -1, 0, 0, 0, 439950000, 250050000, 55)
    send(mav, "set_position_target_global_int_send", 0, 1, 1, frame,
         0b0000111111111000, 439950000, 250050000, 55, 0, 0, 0, 0, 0, 0, 0, 0)
    send(mav, "gps_input_send", 0, 0, 0, 0, 0, 3, 439970000, 250020000, 40,
         1.0, 1.0, 0, 0, 0, 1.0, 1.0, 1.0, 12)
    send(mav, "hil_gps_send", 0, 3, 439970000, 250020000, 40000,
         100, 100, 0, 0, 0, 0, 0, 12)
    send(mav, "mission_count_send", 1, 1, 2)
    send(mav, "mission_item_int_send", 1, 1, 0, frame,
         dialect.MAV_CMD_NAV_WAYPOINT, 1, 1, 0, 0, 0, 0,
         439950000, 250050000, 60)
    send(mav, "mission_clear_all_send", 1, 1)
    send(mav, "param_set_send", 1, 1, b"GF_ACTION", 0.0,
         dialect.MAV_PARAM_TYPE_INT32)
    return sink.frames


def decoys_for(dialect) -> list[bytes]:
    """HEARTBEATs, which no rule names, with every rule's msgid in the payload.

    v1 places one msgid in each of the first five payload bytes, v2 a 24-bit
    msgid at payload+0 and another at payload+3.
    """
    sink = Sink()
    mav = dialect.MAVLink(sink, srcSystem=255, srcComponent=190)
    if dialect is v1:
        # payload+0..3 is custom_mode, payload+4 is type
        for i in range(0, len(RULE_MSGIDS), 5):
            ids = RULE_MSGIDS[i:i + 5]
            mav.heartbeat_send(ids[4], dialect.MAV_AUTOPILOT_INVALID, 0,
                               int.from_bytes(bytes(ids[:4]), "little"), 0)
    else:
        # custom_mode bytes a,0,0,b then type and autopilot both 0
        for a, b in zip(RULE_MSGIDS[::2], RULE_MSGIDS[1::2]):
            mav.heartbeat_send(0, 0, 0, a | b << 24, 0)
    return sink.frames


def udp_packet(payload: bytes) -> bytes:
    """Wrap a frame in UDP/IPv4/Ethernet, with both checksums left at zero."""
    udp = struct.pack("!HHHH", 49152, PORT, 8 + len(payload), 0) + payload
    ip = struct.pack(
        "!BBHHHBBH4s4s", 0x45, 0, 20 + len(udp), 0, 0, 64, socket.IPPROTO_UDP, 0,
        socket.inet_aton(ATTACKER), socket.inet_aton(DRONE))
    eth = b"\x02\x00\x00\x00\x00\x02" + b"\x02\x00\x00\x00\x00\x01" + b"\x08\x00"
    return eth + ip + udp


def main() -> int:
    frames = frames_for(v1) + frames_for(v2) + decoys_for(v1) + decoys_for(v2)
    packets = [udp_packet(f) for f in frames]
    out = Path(__file__).with_name("mavlink-attacks.pcap")
    with out.open("wb") as fh:
        # libpcap header: magic, v2.4, no tz/sigfigs, 65535 snaplen, Ethernet.
        fh.write(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))
        for i, pkt in enumerate(packets):
            fh.write(struct.pack("<IIII", 1758429600, i * 1000, len(pkt), len(pkt)))
            fh.write(pkt)
    v1_count = sum(1 for p in packets if p[42] == 0xFE)
    v2_count = sum(1 for p in packets if p[42] == 0xFD)
    print(f"{out}: {len(packets)} packets ({v1_count} v1, {v2_count} v2)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
