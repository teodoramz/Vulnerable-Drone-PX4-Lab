from __future__ import annotations

import asyncio
import contextlib

import pytest

from app.mavlink.transport import MavlinkTransport
from app.mock.simulator import MockSimulator, SimDrone

HOME_LAT = 44.3222
HOME_LON = 28.0553
HOME_ALT = 25.0


class RecvProtocol(asyncio.DatagramProtocol):
    """Queues incoming UDP datagrams, standing in for a GCS/attacker tool."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()

    def datagram_received(self, data: bytes, addr) -> None:  # noqa: D401
        self.queue.put_nowait(data)

    async def recv(self, timeout: float = 2.0) -> bytes:
        return await asyncio.wait_for(self.queue.get(), timeout=timeout)


@pytest.fixture
def sim() -> MockSimulator:
    drone = SimDrone(id=0, callsign="Sentinel", home_lat=HOME_LAT, home_lon=HOME_LON, home_alt=HOME_ALT)
    simulator = MockSimulator([drone])
    simulator.power(0, True)
    return simulator


@pytest.fixture
async def physics(sim: MockSimulator):
    """Runs the app/main.py physics loop (20 Hz) in the background."""

    async def _loop() -> None:
        while True:
            sim.step(0.05)
            await asyncio.sleep(0.05)

    task = asyncio.create_task(_loop())
    yield task
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


@pytest.fixture
async def transport(sim: MockSimulator):
    t = MavlinkTransport(sim, host="127.0.0.1", port=0)
    await t.start()
    yield t
    await t.stop()


@pytest.fixture
async def client(transport: MavlinkTransport):
    """A UDP socket standing in for an attacker/GCS tool, connected to the transport."""
    loop = asyncio.get_running_loop()
    server_addr = transport._socket.get_extra_info("sockname")
    sock_transport, protocol = await loop.create_datagram_endpoint(
        RecvProtocol, local_addr=("127.0.0.1", 0), remote_addr=server_addr
    )
    yield sock_transport, protocol
    sock_transport.close()
