from fastapi.testclient import TestClient

from app.main import app


def _token(client: TestClient, username: str, password: str) -> str:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_auth_rbac_and_users():
    with TestClient(app) as client:
        # bad credentials
        assert client.post("/api/auth/login", json={"username": "admin", "password": "x"}).status_code == 401

        admin = _token(client, "admin", "Admin1Admin1")
        observer = _token(client, "observer", "Admin1Admin1")

        # /me reflects identity + role
        me = client.get("/api/auth/me", headers=_auth(observer)).json()
        assert me["username"] == "observer" and me["role"] == "observer"

        # observer is read-only
        assert client.get("/api/users", headers=_auth(observer)).status_code == 403
        assert client.get("/api/audit", headers=_auth(observer)).status_code == 403
        assert client.get("/api/drones", headers=_auth(observer)).status_code == 200

        # operators may read the audit log
        operator = _token(client, "operator", "Admin1Admin1")
        assert client.get("/api/audit", headers=_auth(operator)).status_code == 200
        # but not admin-only endpoints
        assert client.get("/api/users", headers=_auth(operator)).status_code == 403

        # admin manages users
        assert client.get("/api/users", headers=_auth(admin)).status_code == 200
        created = client.post(
            "/api/users",
            headers=_auth(admin),
            json={"username": "pilot1", "password": "pilot1pw", "role": "operator"},
        )
        assert created.status_code == 201, created.text

        # the new operator can log in and read drones, but not manage users
        pilot = _token(client, "pilot1", "pilot1pw")
        assert client.get("/api/drones", headers=_auth(pilot)).status_code == 200
        assert client.post(
            "/api/users", headers=_auth(pilot),
            json={"username": "z", "password": "zzzz", "role": "observer"},
        ).status_code == 403

        # no auth at all -> 403 (no bearer)
        assert client.get("/api/users").status_code == 403


def test_drone_registry_and_claim_requires_auth():
    with TestClient(app) as client:
        admin = _token(client, "admin", "Admin1Admin1")
        drones = client.get("/api/drones", headers=_auth(admin)).json()
        assert len(drones) >= 1
        assert {"id", "callsign", "enabled", "state", "claim"} <= drones[0].keys()
        # unauthenticated claim attempt is rejected
        assert client.post("/api/drones/0/claim").status_code == 403
