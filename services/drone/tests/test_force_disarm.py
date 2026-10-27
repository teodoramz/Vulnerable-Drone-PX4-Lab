"""Force-disarm ("kill"): ARM_DISARM with param2=21196 drops an airborne drone faster
than a controlled LAND; a plain in-air disarm is refused."""
from __future__ import annotations

import asyncio

from pymavlink.dialects.v20 import common as mavlink2

from tests.helpers import gcs_encoder, recv_command_ack


async def test_plain_disarm_in_air_is_denied(sim, physics, transport, client):
    sock_transport, protocol = client
    drone = sim.drones[0]
    drone.armed = True
    drone.in_air = True
    drone.rel_alt = 50.0
    drone.mode = "IDLE"

    mav = gcs_encoder()
    msg = mav.command_long_encode(
        1, mavlink2.MAV_COMP_ID_AUTOPILOT1, mavlink2.MAV_CMD_COMPONENT_ARM_DISARM, 0,
        0, 0, 0, 0, 0, 0, 0,  # param1=0 (disarm), param2=0 (no force)
    )
    sock_transport.sendto(msg.pack(mav))

    ack = await recv_command_ack(protocol, mavlink2.MAV_CMD_COMPONENT_ARM_DISARM)
    assert ack.result == mavlink2.MAV_RESULT_DENIED
    assert drone.armed is True
    assert drone.mode != "FALLING"


async def test_force_disarm_drops_an_airborne_drone(sim, physics, transport, client):
    sock_transport, protocol = client
    drone = sim.drones[0]
    drone.armed = True
    drone.in_air = True
    drone.rel_alt = 50.0
    drone.mode = "IDLE"

    mav = gcs_encoder()
    msg = mav.command_long_encode(
        1, mavlink2.MAV_COMP_ID_AUTOPILOT1, mavlink2.MAV_CMD_COMPONENT_ARM_DISARM, 0,
        0, 21196, 0, 0, 0, 0, 0,  # param1=0 (disarm), param2=21196 (force)
    )
    sock_transport.sendto(msg.pack(mav))

    ack = await recv_command_ack(protocol, mavlink2.MAV_CMD_COMPONENT_ARM_DISARM)
    assert ack.result == mavlink2.MAV_RESULT_ACCEPTED
    assert drone.armed is False
    assert drone.mode == "FALLING"

    # LAND from 50 m takes 50s; the crash takes ~5.1s (9.8 m/s), so allow 8s.
    for _ in range(160):  # up to 8s of sim time, at 0.05s per tick
        await asyncio.sleep(0.05)
        if drone.rel_alt <= 0.0:
            break
    assert drone.rel_alt <= 0.0
    assert drone.in_air is False
    assert drone.mode == "IDLE"


async def test_force_disarm_on_grounded_drone_is_a_plain_disarm(sim, physics, transport, client):
    sock_transport, protocol = client
    drone = sim.drones[0]
    drone.armed = True
    drone.in_air = False
    drone.rel_alt = 0.0

    mav = gcs_encoder()
    msg = mav.command_long_encode(
        1, mavlink2.MAV_COMP_ID_AUTOPILOT1, mavlink2.MAV_CMD_COMPONENT_ARM_DISARM, 0,
        0, 21196, 0, 0, 0, 0, 0,
    )
    sock_transport.sendto(msg.pack(mav))

    ack = await recv_command_ack(protocol, mavlink2.MAV_CMD_COMPONENT_ARM_DISARM)
    assert ack.result == mavlink2.MAV_RESULT_ACCEPTED
    assert drone.armed is False
    assert drone.mode == "IDLE"  # never enters FALLING -- it was already on the ground
