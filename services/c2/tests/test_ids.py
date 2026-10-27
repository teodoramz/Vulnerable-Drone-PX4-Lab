from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

_SAMPLE_ALERT = {
    "ts": "2026-09-21T12:00:00Z",
    "signature": "ET DRONE MAVLink COMMAND_LONG from non-GCS source",
    "sid": 900001,
    "severity": 2,
    "category": "Potentially Bad Traffic",
    "src_ip": "10.60.0.50",
    "src_port": 55123,
    "dest_ip": "10.60.0.10",
    "dest_port": 14550,
    "proto": "UDP",
    "iface": "eth0",
}


def _token(client: TestClient, username: str, password: str) -> str:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _push(client: TestClient, alert: dict, token: str | None = settings.ids_push_token):
    headers = {"X-IDS-Token": token} if token is not None else {}
    return client.post("/api/ids/alerts", json=alert, headers=headers)


def test_ingest_requires_valid_token():
    with TestClient(app) as client:
        # missing token
        assert _push(client, _SAMPLE_ALERT, token=None).status_code == 401
        # wrong token
        assert _push(client, _SAMPLE_ALERT, token="not-the-token").status_code == 401
        # correct token
        r = _push(client, _SAMPLE_ALERT)
        assert r.status_code == 201, r.text


def test_ingested_alert_appears_in_get():
    with TestClient(app) as client:
        operator = _token(client, settings.operator_username, settings.operator_password)
        alert = dict(_SAMPLE_ALERT, sid=900002, signature="unique-signature-for-get-test")
        assert _push(client, alert).status_code == 201

        r = client.get("/api/ids/alerts", headers=_auth(operator))
        assert r.status_code == 200
        sigs = [a["signature"] for a in r.json()]
        assert "unique-signature-for-get-test" in sigs


def test_severity_filter():
    with TestClient(app) as client:
        operator = _token(client, settings.operator_username, settings.operator_password)
        low = dict(_SAMPLE_ALERT, sid=900003, signature="sev-low-marker", severity=1)
        high = dict(_SAMPLE_ALERT, sid=900004, signature="sev-high-marker", severity=3)
        assert _push(client, low).status_code == 201
        assert _push(client, high).status_code == 201

        r = client.get("/api/ids/alerts", headers=_auth(operator), params={"severity": 3})
        assert r.status_code == 200
        sigs = [a["signature"] for a in r.json()]
        assert "sev-high-marker" in sigs
        assert "sev-low-marker" not in sigs


def test_observer_can_read_alerts_but_not_command_drone():
    with TestClient(app) as client:
        observer = _token(client, settings.observer_username, settings.observer_password)
        alert = dict(_SAMPLE_ALERT, sid=900005, signature="observer-read-marker")
        assert _push(client, alert).status_code == 201

        # monitoring data is not privileged -> observer can read it
        r = client.get("/api/ids/alerts", headers=_auth(observer))
        assert r.status_code == 200
        assert "observer-read-marker" in [a["signature"] for a in r.json()]

        # but an observer still cannot claim/command a drone
        assert client.post("/api/drones/0/claim", headers=_auth(observer)).status_code == 403


def test_ws_broadcast_fires_on_ingest():
    with TestClient(app) as client:
        operator = _token(client, settings.operator_username, settings.operator_password)
        with client.websocket_connect(f"/ws?token={operator}") as ws:
            # drain the priming frames (logs, telemetry, any prior alerts)
            drained = []
            for _ in range(50):
                drained.append(ws.receive_json())
                if drained[-1]["type"] == "telemetry":
                    break

            alert = dict(_SAMPLE_ALERT, sid=900006, signature="ws-broadcast-marker")
            assert _push(client, alert).status_code == 201

            for _ in range(20):
                msg = ws.receive_json()
                if msg.get("type") == "ids_alert" and msg["alert"]["signature"] == "ws-broadcast-marker":
                    break
            else:
                raise AssertionError("ids_alert broadcast for the ingested alert was not received")


def test_portless_alert_is_accepted():
    """Port-less alerts (ICMP etc.) must be accepted."""
    with TestClient(app) as client:
        r = _push(client, {
            "ts": "2026-09-21T04:30:00Z",
            "signature": "OT LAB Recon - ICMP sweep across segment",
            "sid": 9000101,
            "severity": 2,
            "src_ip": "10.10.30.66",
            "dest_ip": "10.10.20.10",
            "proto": "ICMP",
        })
        assert r.status_code == 201, r.text

        admin = _token(client, settings.admin_username, settings.admin_password)
        got = client.get("/api/ids/alerts", headers=_auth(admin)).json()
        match = [a for a in got if a["sid"] == 9000101]
        assert match, "port-less alert did not reach the buffer"
        assert match[0]["src_port"] is None and match[0]["dest_port"] is None
