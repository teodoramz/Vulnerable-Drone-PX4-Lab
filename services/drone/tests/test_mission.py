"""Waypoint injection (`waypoint`): the MISSION_COUNT / MISSION_ITEM_INT handshake
stores the waypoints and the drone starts flying them."""
from __future__ import annotations

import asyncio

import pytest
from pymavlink.dialects.v20 import common as mavlink2

from tests.helpers import gcs_encoder, recv_typed


async def test_mission_upload_stores_waypoints_and_starts_flying(sim, physics, transport, client):
    sock_transport, protocol = client
    drone = sim.drones[0]

    mav = gcs_encoder()
    waypoints = [
        (drone.home_lat + 0.001, drone.home_lon + 0.001, 20.0),
        (drone.home_lat + 0.002, drone.home_lon + 0.0005, 25.0),
    ]

    count_msg = mav.mission_count_encode(1, mavlink2.MAV_COMP_ID_AUTOPILOT1, len(waypoints))
    sock_transport.sendto(count_msg.pack(mav))

    for seq, (lat, lon, alt) in enumerate(waypoints):
        req = await recv_typed(protocol, "MISSION_REQUEST_INT")
        assert req.seq == seq
        item = mav.mission_item_int_encode(
            1, mavlink2.MAV_COMP_ID_AUTOPILOT1, seq,
            mavlink2.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT, mavlink2.MAV_CMD_NAV_WAYPOINT,
            0, 1, 0.0, 0.0, 0.0, 0.0,
            int(round(lat * 1e7)), int(round(lon * 1e7)), alt,
        )
        sock_transport.sendto(item.pack(mav))

    ack = await recv_typed(protocol, "MISSION_ACK")
    assert ack.type == mavlink2.MAV_MISSION_ACCEPTED

    assert len(drone.mission_items) == 2
    for (lat, lon, alt), stored in zip(waypoints, drone.mission_items):
        assert stored[0] == pytest.approx(lat, rel=1e-6)
        assert stored[1] == pytest.approx(lon, rel=1e-6)
        assert stored[2] == pytest.approx(alt, rel=1e-6)

    # Upload arms the drone and starts the mission immediately.
    assert drone.armed is True
    assert drone.mode == "MISSION"

    start_lat, start_lon = drone.lat, drone.lon
    for _ in range(20):
        await asyncio.sleep(0.05)
    assert (drone.lat, drone.lon) != (start_lat, start_lon)


async def test_mission_count_zero_clears_and_acks(sim, physics, transport, client):
    sock_transport, protocol = client
    drone = sim.drones[0]
    drone.mission_items = [(1.0, 2.0, 3.0)]

    mav = gcs_encoder()
    count_msg = mav.mission_count_encode(1, mavlink2.MAV_COMP_ID_AUTOPILOT1, 0)
    sock_transport.sendto(count_msg.pack(mav))

    ack = await recv_typed(protocol, "MISSION_ACK")
    assert ack.type == mavlink2.MAV_MISSION_ACCEPTED
    assert drone.mission_items == []
