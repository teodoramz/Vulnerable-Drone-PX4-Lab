import asyncio
import json

import pytest

from app.config import Settings
from app.models import Alert
from app.state import SensorState


class _RecordingPusher:
    def __init__(self) -> None:
        self.pushed: list[Alert] = []

    async def push(self, alert: Alert) -> bool:
        self.pushed.append(alert)
        return True

    async def aclose(self) -> None:
        pass


def _alert_line(sid: int, severity: int, ts: str = "2026-09-21T04:20:00+0000") -> str:
    return json.dumps({
        "timestamp": ts,
        "event_type": "alert",
        "src_ip": "10.0.0.5", "src_port": 4444,
        "dest_ip": "10.0.0.6", "dest_port": 14550,
        "proto": "UDP",
        "in_iface": "ot-air",
        "alert": {"signature_id": sid, "signature": f"sig-{sid}", "severity": severity, "category": "c"},
    })


def _flow_line(ts: str = "2026-09-21T04:20:00+0000") -> str:
    return json.dumps({
        "timestamp": ts,
        "event_type": "flow",
        "src_ip": "10.0.0.5", "src_port": 4444,
        "dest_ip": "10.0.0.6", "dest_port": 14550,
        "proto": "UDP",
        "in_iface": "ot-air",
        "flow": {"pkts_toserver": 1, "state": "new"},
    })


@pytest.mark.asyncio
async def test_process_line_buffers_alert_and_broadcasts():
    settings = Settings(alert_buffer_size=10, flow_buffer_size=10)
    state = SensorState(settings, pusher=_RecordingPusher())

    sent = []

    class FakeWs:
        async def send_text(self, text):
            sent.append(json.loads(text))

    state.hub.connect(FakeWs())

    record = await state.process_line(_alert_line(9000001, 1))

    assert isinstance(record, Alert)
    assert len(state.alerts) == 1
    assert sent == [{"type": "alert", "data": record.model_dump()}]
    assert state.last_event_ts == "2026-09-21T04:20:00+0000"


@pytest.mark.asyncio
async def test_process_line_buffers_flow_and_broadcasts():
    settings = Settings(alert_buffer_size=10, flow_buffer_size=10)
    state = SensorState(settings, pusher=_RecordingPusher())
    record = await state.process_line(_flow_line())
    assert len(state.flows) == 1
    assert len(state.alerts) == 0
    assert record.pkts_toserver == 1


@pytest.mark.asyncio
async def test_process_line_ignores_unparsable_line():
    settings = Settings(alert_buffer_size=10, flow_buffer_size=10)
    state = SensorState(settings, pusher=_RecordingPusher())
    record = await state.process_line("not json")
    assert record is None
    assert len(state.alerts) == 0
    assert len(state.flows) == 0


@pytest.mark.asyncio
async def test_alert_is_queued_for_push():
    settings = Settings(alert_buffer_size=10, flow_buffer_size=10)
    pusher = _RecordingPusher()
    state = SensorState(settings, pusher=pusher)

    await state.process_line(_alert_line(9000003, 1))
    assert state.push_queue.qsize() == 1

    # Run the real push loop briefly to confirm it drains the queue via
    # the pusher, then stop it again.
    await state.start()
    await asyncio.sleep(0.1)
    await state.stop()

    assert len(pusher.pushed) == 1
    assert pusher.pushed[0].sid == 9000003


@pytest.mark.asyncio
async def test_push_failure_never_raises_out_of_process_line():
    class _AlwaysFailsPusher:
        async def push(self, alert):
            raise RuntimeError("C2 is on fire")

        async def aclose(self):
            pass

    settings = Settings(alert_buffer_size=10, flow_buffer_size=10)
    state = SensorState(settings, pusher=_AlwaysFailsPusher())

    # process_line itself must not raise even though the eventual push will.
    await state.process_line(_alert_line(9000001, 2))

    await state.start()
    await asyncio.sleep(0.1)
    # The push loop must still be alive despite the pusher raising.
    assert state._push_task is not None and not state._push_task.done()
    await state.stop()
