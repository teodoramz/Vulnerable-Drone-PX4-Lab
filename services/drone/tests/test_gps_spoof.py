"""GPS spoofing (`gpsspoof`): an unauthenticated GPS_INPUT moves the drone's position."""
from __future__ import annotations

import asyncio

import pytest
from pymavlink.dialects.v20 import common as mavlink2

from tests.helpers import gcs_encoder


async def test_gps_input_shifts_position(sim, physics, transport, client):
    sock_transport, protocol = client
    drone = sim.drones[0]
    original_lat, original_lon = drone.lat, drone.lon

    spoof_lat = original_lat + 0.05   # ~5.5 km north
    spoof_lon = original_lon + 0.05
    spoof_alt = drone.home_alt + 40.0  # AMSL

    mav = gcs_encoder()
    msg = mav.gps_input_encode(
        0, 0, 0,  # time_usec, gps_id, ignore_flags (nothing ignored)
        0, 0,     # time_week_ms, time_week
        mavlink2.GPS_FIX_TYPE_3D_FIX,
        int(round(spoof_lat * 1e7)),
        int(round(spoof_lon * 1e7)),
        spoof_alt,
        1.0, 1.0,          # hdop, vdop
        0.0, 0.0, 0.0,     # vn, ve, vd
        0.5, 1.0, 1.0,     # speed_accuracy, horiz_accuracy, vert_accuracy
        10,                # satellites_visible
    )
    sock_transport.sendto(msg.pack(mav))

    # Poll until the transport has applied it.
    for _ in range(40):
        await asyncio.sleep(0.05)
        if abs(drone.lat - original_lat) > 1e-6:
            break

    assert drone.lat != original_lat
    assert drone.lon != original_lon
    assert drone.lat == pytest.approx(spoof_lat, rel=1e-4)
    assert drone.lon == pytest.approx(spoof_lon, rel=1e-4)
    assert drone.rel_alt == pytest.approx(40.0, rel=1e-3)


async def test_gps_input_altitude_ignore_flag_is_honored(sim, physics, transport, client):
    sock_transport, protocol = client
    drone = sim.drones[0]
    drone.rel_alt = 12.5
    original_alt = drone.rel_alt
    original_lat = drone.lat

    mav = gcs_encoder()
    msg = mav.gps_input_encode(
        0, 0, mavlink2.GPS_INPUT_IGNORE_FLAG_ALT,
        0, 0,
        mavlink2.GPS_FIX_TYPE_3D_FIX,
        int(round((drone.lat + 0.01) * 1e7)),
        int(round(drone.lon * 1e7)),
        9999.0,  # would be a huge altitude jump if not ignored
        1.0, 1.0,
        0.0, 0.0, 0.0,
        0.5, 1.0, 1.0,
        10,
    )
    sock_transport.sendto(msg.pack(mav))

    for _ in range(40):
        await asyncio.sleep(0.05)
        if abs(drone.lat - original_lat) > 1e-6:
            break

    assert drone.lat != original_lat  # position still applied
    assert drone.rel_alt == pytest.approx(original_alt, abs=1e-6)  # altitude untouched
