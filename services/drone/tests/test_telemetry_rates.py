"""Telemetry emission rates must be approximately correct: HEARTBEAT at
1 Hz, GLOBAL_POSITION_INT at 10 Hz, per the design doc."""
from __future__ import annotations

import asyncio

from tests.helpers import decoder, register_as_peer


async def _count_messages_over(protocol, type_name: str, duration: float) -> int:
    dec = decoder()
    count = 0
    loop = asyncio.get_running_loop()
    deadline = loop.time() + duration
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        try:
            data = await asyncio.wait_for(protocol.recv(timeout=remaining), timeout=remaining)
        except asyncio.TimeoutError:
            break
        for msg in dec.parse_buffer(bytearray(data)):
            if msg.get_type() == type_name:
                count += 1
    return count


async def test_heartbeat_emitted_at_approximately_1hz(sim, physics, transport, client):
    sock_transport, protocol = client
    await register_as_peer(sock_transport)
    count = await _count_messages_over(protocol, "HEARTBEAT", 3.2)
    # 1 Hz over ~3.2s -> ~3; generous slack for scheduler jitter under load.
    assert 2 <= count <= 5


async def test_global_position_int_emitted_at_approximately_10hz(sim, physics, transport, client):
    sock_transport, protocol = client
    await register_as_peer(sock_transport)
    count = await _count_messages_over(protocol, "GLOBAL_POSITION_INT", 2.0)
    # 10 Hz over 2s -> ~20; generous slack for scheduler jitter under load.
    assert 12 <= count <= 28
