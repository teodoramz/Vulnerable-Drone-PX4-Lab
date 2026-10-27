"""HEARTBEAT and GLOBAL_POSITION_INT must be valid MAVLink 2 frames from
system 1 / MAV_COMP_ID_AUTOPILOT1 carrying real simulator state."""
from __future__ import annotations

import pytest
from pymavlink.dialects.v20 import common as mavlink2

from tests.helpers import recv_typed, register_as_peer


async def test_heartbeat_is_valid_mavlink2_with_correct_identity_and_fields(sim, physics, transport, client):
    sock_transport, protocol = client
    await register_as_peer(sock_transport)

    hb = await recv_typed(protocol, "HEARTBEAT")

    # Sourced from system 1 / component 1, per the design doc.
    assert hb.get_srcSystem() == 1
    assert hb.get_srcComponent() == mavlink2.MAV_COMP_ID_AUTOPILOT1

    assert hb.type == mavlink2.MAV_TYPE_QUADROTOR
    assert hb.autopilot == mavlink2.MAV_AUTOPILOT_PX4

    drone = sim.drones[0]
    assert bool(hb.base_mode & mavlink2.MAV_MODE_FLAG_SAFETY_ARMED) == drone.armed
    assert bool(hb.base_mode & mavlink2.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED)


async def test_global_position_int_matches_simulator_state(sim, physics, transport, client):
    sock_transport, protocol = client
    await register_as_peer(sock_transport)

    drone = sim.drones[0]
    gpi = await recv_typed(protocol, "GLOBAL_POSITION_INT")

    assert gpi.lat == pytest.approx(round(drone.lat * 1e7), abs=5)
    assert gpi.lon == pytest.approx(round(drone.lon * 1e7), abs=5)
    assert gpi.relative_alt == pytest.approx(round(drone.rel_alt * 1000), abs=50)
    assert gpi.alt == pytest.approx(round(drone.abs_alt * 1000), abs=50)


async def test_gps_raw_int_and_sys_status_and_attitude_are_decodable(sim, physics, transport, client):
    sock_transport, protocol = client
    await register_as_peer(sock_transport)

    gps = await recv_typed(protocol, "GPS_RAW_INT")
    assert gps.fix_type == mavlink2.GPS_FIX_TYPE_3D_FIX

    status = await recv_typed(protocol, "SYS_STATUS")
    assert status.battery_remaining == 100

    att = await recv_typed(protocol, "ATTITUDE")
    assert -3.2 <= att.yaw <= 3.2  # radians, wrapped

    ext = await recv_typed(protocol, "EXTENDED_SYS_STATE")
    assert ext.landed_state in (
        mavlink2.MAV_LANDED_STATE_ON_GROUND,
        mavlink2.MAV_LANDED_STATE_IN_AIR,
        mavlink2.MAV_LANDED_STATE_LANDING,
    )
