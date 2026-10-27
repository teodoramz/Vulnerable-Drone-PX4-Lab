import pytest
from fastapi.testclient import TestClient

from app.main import app, state
from app.models import Alert, Flow


@pytest.fixture(scope="module")
def client():
    # One shared TestClient: `state`'s asyncio.Queue binds to the first event loop that uses it.
    with TestClient(app) as c:
        yield c


def _alert(sid=9000001, severity=1, ts="2026-09-21T04:20:00+0000") -> Alert:
    return Alert(
        ts=ts, signature=f"sig-{sid}", sid=sid, severity=severity, category="cat",
        src_ip="10.0.0.5", src_port=1111, dest_ip="10.0.0.6", dest_port=14550, proto="UDP", iface="ot-air",
    )


def _flow(ts="2026-09-21T04:20:00+0000") -> Flow:
    return Flow(
        ts=ts, src_ip="10.0.0.5", src_port=1111, dest_ip="10.0.0.6", dest_port=14550,
        proto="UDP", iface="ot-air", state="new", pkts_toserver=3,
    )


def setup_function(_):
    # Each test starts from a clean buffer regardless of test order.
    state.alerts._items.clear()
    state.flows._items.clear()


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "eve_path" in body
    assert body["ifaces"] == ["ot-ops", "ot-air"]


def test_alerts_endpoint_returns_buffered_alerts(client):
    state.alerts.append(_alert(sid=9000001))
    state.alerts.append(_alert(sid=9000002))
    r = client.get("/alerts")
    assert r.status_code == 200
    sids = [a["sid"] for a in r.json()]
    assert sids == [9000001, 9000002]


def test_alerts_endpoint_severity_filter(client):
    state.alerts.append(_alert(sid=1, severity=1))
    state.alerts.append(_alert(sid=2, severity=2))
    state.alerts.append(_alert(sid=3, severity=1))
    r = client.get("/alerts", params={"severity": 1})
    assert r.status_code == 200
    sids = [a["sid"] for a in r.json()]
    assert sids == [1, 3]


def test_alerts_endpoint_since_filter(client):
    state.alerts.append(_alert(sid=1, ts="2026-09-21T04:00:00+00:00"))
    state.alerts.append(_alert(sid=2, ts="2026-09-21T04:10:00+00:00"))
    state.alerts.append(_alert(sid=3, ts="2026-09-21T04:20:00+00:00"))
    r = client.get("/alerts", params={"since": "2026-09-21T04:05:00+00:00"})
    sids = [a["sid"] for a in r.json()]
    assert sids == [2, 3]


def test_alerts_endpoint_limit(client):
    for i in range(5):
        state.alerts.append(_alert(sid=i))
    r = client.get("/alerts", params={"limit": 2})
    sids = [a["sid"] for a in r.json()]
    assert sids == [3, 4]


def test_flows_endpoint_returns_buffered_flows(client):
    state.flows.append(_flow())
    r = client.get("/flows")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["pkts_toserver"] == 3


def test_ws_primes_client_with_buffered_alerts_and_flows(client):
    state.alerts.append(_alert(sid=42))
    state.flows.append(_flow())
    with client.websocket_connect("/ws") as ws:
        first = ws.receive_json()
        second = ws.receive_json()
    kinds = {first["type"], second["type"]}
    assert kinds == {"alert", "flow"}
    alert_msg = first if first["type"] == "alert" else second
    assert alert_msg["data"]["sid"] == 42
