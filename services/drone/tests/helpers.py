from __future__ import annotations

from pymavlink.dialects.v20 import common as mavlink2


def gcs_encoder() -> mavlink2.MAVLink:
    """MAVLink encoder for outbound test frames (sysid 255, the GCS convention)."""
    mav = mavlink2.MAVLink(None, srcSystem=255, srcComponent=190)
    mav.robust_parsing = True
    return mav


def decoder() -> mavlink2.MAVLink:
    mav = mavlink2.MAVLink(None)
    mav.robust_parsing = True
    return mav


async def register_as_peer(sock_transport) -> None:
    """Send one heartbeat so the transport adds us to its broadcast peer set."""
    mav = gcs_encoder()
    hello = mav.heartbeat_encode(
        mavlink2.MAV_TYPE_GCS, mavlink2.MAV_AUTOPILOT_INVALID, 0, 0, mavlink2.MAV_STATE_ACTIVE
    )
    sock_transport.sendto(hello.pack(mav))


async def recv_typed(protocol, type_name: str, timeout: float = 3.0, attempts: int = 300):
    """Read datagrams until one decodes to MAVLink `type_name`, skipping interleaved telemetry."""
    dec = decoder()
    for _ in range(attempts):
        data = await protocol.recv(timeout=timeout)
        for msg in dec.parse_buffer(bytearray(data)):
            if msg.get_type() == type_name:
                return msg
    raise AssertionError(f"did not see a {type_name} within {attempts} datagrams")


async def recv_command_ack(protocol, command: int, timeout: float = 3.0, attempts: int = 300):
    dec = decoder()
    for _ in range(attempts):
        data = await protocol.recv(timeout=timeout)
        for msg in dec.parse_buffer(bytearray(data)):
            if msg.get_type() == "COMMAND_ACK" and msg.command == command:
                return msg
    raise AssertionError(f"did not see a COMMAND_ACK for command {command} within {attempts} datagrams")
