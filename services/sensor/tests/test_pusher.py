import httpx
import pytest

from app.config import Settings
from app.models import Alert
from app.pusher import AlertPusher

ALERT = Alert(
    ts="2026-09-21T04:20:00+0000", signature="test sig", sid=9000001, severity=1,
    category="", src_ip="1.1.1.1", src_port=1234, dest_ip="2.2.2.2", dest_port=14550,
    proto="UDP", iface="ot-air",
)


def _settings(**overrides) -> Settings:
    base = dict(
        c2_url="http://c2.invalid",
        ids_push_token="test-token",
        push_max_retries=3,
        push_base_delay=0.01,
        push_max_delay=0.02,
        push_timeout=1.0,
    )
    base.update(overrides)
    return Settings(**base)


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _FailingClient:
    """Simulates the C2 being completely unreachable."""

    def __init__(self) -> None:
        self.calls = 0

    async def post(self, url, json=None, headers=None):
        self.calls += 1
        raise httpx.ConnectError("connection refused", request=None)


class _AlwaysNotFoundClient:
    """Simulates the C2 returning 404 for /api/ids/alerts."""

    def __init__(self) -> None:
        self.calls = 0

    async def post(self, url, json=None, headers=None):
        self.calls += 1
        return _FakeResponse(404, "Not Found")


class _FlakyThenOkClient:
    """Fails twice, then succeeds on the 3rd attempt."""

    def __init__(self) -> None:
        self.calls = 0

    async def post(self, url, json=None, headers=None):
        self.calls += 1
        if self.calls < 3:
            raise httpx.ConnectError("connection refused", request=None)
        return _FakeResponse(201, "ok")


class _RecordingOkClient:
    def __init__(self) -> None:
        self.calls = []

    async def post(self, url, json=None, headers=None):
        self.calls.append((url, json, headers))
        return _FakeResponse(201, "ok")


@pytest.mark.asyncio
async def test_push_retries_and_gives_up_when_c2_unreachable(caplog):
    settings = _settings(push_max_retries=3)
    client = _FailingClient()
    pusher = AlertPusher(settings, client=client)

    caplog.set_level("WARNING")
    ok = await pusher.push(ALERT)

    assert ok is False
    assert client.calls == 3  # respected push_max_retries, did not hang forever
    assert any("giving up" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_push_logs_and_continues_on_404(caplog):
    """A 404 is a soft failure (log, retry, give up), never an exception from push()."""
    settings = _settings(push_max_retries=2)
    client = _AlwaysNotFoundClient()
    pusher = AlertPusher(settings, client=client)

    caplog.set_level("WARNING")
    ok = await pusher.push(ALERT)

    assert ok is False
    assert client.calls == 2
    assert any("404" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_push_succeeds_after_transient_failures():
    settings = _settings(push_max_retries=5)
    client = _FlakyThenOkClient()
    pusher = AlertPusher(settings, client=client)

    ok = await pusher.push(ALERT)

    assert ok is True
    assert client.calls == 3


@pytest.mark.asyncio
async def test_push_sends_exact_contract_shape_and_auth_header():
    settings = _settings(c2_url="http://c2:8000", ids_push_token="s3cr3t")
    client = _RecordingOkClient()
    pusher = AlertPusher(settings, client=client)

    ok = await pusher.push(ALERT)

    assert ok is True
    url, body, headers = client.calls[0]
    assert url == "http://c2:8000/api/ids/alerts"
    assert headers == {"X-IDS-Token": "s3cr3t"}
    assert body == {
        "ts": "2026-09-21T04:20:00+0000",
        "signature": "test sig",
        "sid": 9000001,
        "severity": 1,
        "category": "",
        "src_ip": "1.1.1.1",
        "src_port": 1234,
        "dest_ip": "2.2.2.2",
        "dest_port": 14550,
        "proto": "UDP",
        "iface": "ot-air",
        # Suricata's payload logging carries the bytes that tripped the
        # rule; empty here because this fixture alert has none.
        "payload": "",
        "payload_printable": "",
    }
