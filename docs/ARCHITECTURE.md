# Architecture and development

Network layout, ports and deployment: `docs/INFRASTRUCTURE.md`. This document covers the software and local development.

## The DroneLink boundary

The C2 contains no physics. It powers the drone through the lifecycle API (`:9100`) and flies it through the `DroneLink` interface (`services/c2/app/dronelink/base.py`): `connect`, `arm`, `set_velocity_ned`, `goto_location`, `land`, `hold`.

| Adapter | Backend | Transport |
|---|---|---|
| `MavsdkLink` | `px4` | MAVLink via MAVSDK |
| `MockLink` | `mock` | WebSocket verb protocol to the mock |

Both backends speak MAVLink 2. The toolkit sends v1 until the peer answers in v2, so each MAVLink rule has a v1 and a v2 sid (`docs/MONITORING.md`). The mock has no EKF, failsafes or real parameters (`docs/SIMULATION.md`).

## Flight state machine

One async control loop per drone runs in `app/services/fleet.py`. Commands set a requested state and the loop drives toward it.

```
OFFLINE -> BOOTING -> IDLE -> TAKEOFF -> HOVER
HOVER <-> GOTO        (arrived: GOTO -> HOVER)
HOVER <-> PATROL      (CANCEL: PATROL -> HOVER; waypoints loop)
HOVER <-> MANUAL
HOVER / GOTO / PATROL -> LAND -> IDLE -> OFFLINE (power off)
HOVER / GOTO / PATROL / MANUAL -> SIGNAL_LOST -> OFFLINE -> (maintenance reset) -> IDLE
```

- `SIGNAL_LOST` is the single loss state for both a structure strike and a boundary crossing. The real cause is held on the runtime for internal use and is not logged, audited or served.
- Each tick tests position against the operational polygon and all 15,793 objects (`app/services/site.py`, a 100 m grid over `app/data/airport_objects.json`). Debounce: 5 ticks outside the boundary (`BOUNDARY_BREACH_TICKS`), 3 inside an obstacle (`COLLISION_TICKS`).
- Takeoff is restricted to the dataset's helipads; a wreck cannot be revived by the power switch.
- `ALTITUDE` is not a state. It re-issues the current activity at the new height; in `HOVER` the engine flies to the current position at the new altitude.
- `PATROL` advances within `PATROL_ARRIVE_M` (3 m). Flight commands are audited; telemetry broadcasts at 10 Hz over `/ws`.

## Command and telemetry path

```
operator -> POST /api/drones/0/power -> c2 -> POST /drones/0/power (:9100) -> drone agent spawns px4 (SIH)
px4 -> MAVLink -> drone agent -> relay to c2:14540/udp
c2 -> arm / offboard setpoints (MAVSDK) -> px4
c2 -> telemetry + logs over /ws -> operators
sensor -> POST /api/ids/alerts (X-IDS-Token) -> c2 -> {"type":"ids_alert"} over /ws
```

Alerts share the operator WebSocket so only one port crosses the boundary. A compromised C2 can suppress them; `sensor:9200` is independent.

## Claims and roles

- Only the operator holding a drone's claim can command it. Admins can force-release. Claims live in memory with a TTL (`CLAIM_TTL_SECONDS`, 120) and are kept alive while the holder's WebSocket is open.
- Roles:

| Role | Permissions |
|---|---|
| `admin` | everything, including user management and force-release |
| `operator` | read, power, claim, command, missions, read audit log |
| `observer` | read drones and missions only |

- `swarm.py` computes lateral anti-collision offsets. With `DRONE_COUNT` above 1 the swarm UI (multi-select, broadcast) appears.

## API summary

| Prefix | Notes |
|---|---|
| `/api/auth` | `POST /login`, `GET /me` |
| `/api/drones` | list; `POST /{id}/claim`, `/release`, `/force-release`, `/reset`, `/power` |
| `/api/missions` | list, create, get |
| `/api/audit` | `audit:read` (admin, operator); `limit`, `offset`, `drone_id` |
| `/api/site` | site definition; `/objects` (filter, near-position search), `/objects/at`, `/objects/{id}` |
| `/api/ids` | `POST /alerts` (sensor token); `GET /alerts`, `/flows`, `/live`, `/packets`, `/breakdown`, `/captures`, `/captures/{name}` |
| `/api/users` | admin user management |
| `/api/public` | `GET /drone`, `GET /drones`, unauthenticated (`docs/PUBLIC-API.md`) |
| `/ws` | telemetry, logs, IDS alerts, commands |
| `/health` | liveness (also on drone agent `:9100` and sensor `:9200`) |

Interactive docs: `http://<c2>:8000/docs`.

## Repository layout

```
docker-compose.yml          single-host stack (PX4)
docker-compose.mock.yml     override: mock backend
docker-compose.attacker.yml override: pivot container
env.example                 single-host configuration
deploy/                     one compose file per component (multi-VM)
ansible/                    single-host deploy role
services/frontend           gcs: React console + nginx
services/c2                 mission server and fleet engine
services/drone              PX4 SITL (px4/) or mock (app/mock, app/mavlink)
services/sensor             Suricata, rules, FastAPI sidecar
tools/                      exploit kit (exploit.py, hijack.py, dataset)
scripts/                    check-ids-contract.py, check-kit-parity.py, mavlink_attacks.sh
assets/                     map source (assets/README.md)
docs/                       documentation
```

## Development

Each service has its own virtualenv and test suite.

```bash
python3 -m venv .venv-c2 && .venv-c2/bin/pip install -r services/c2/requirements.txt
(cd services/c2 && ../../.venv-c2/bin/python -m pytest -q)

python3 -m venv .venv-drone && .venv-drone/bin/pip install -r services/drone/requirements.txt
(cd services/drone && ../../.venv-drone/bin/python -m pytest -q)

python3 -m venv .venv-sensor && .venv-sensor/bin/pip install -r services/sensor/requirements.txt
(cd services/sensor && ../../.venv-sensor/bin/python -m pytest -q)

(cd services/frontend && npm install && npm run build)    # typecheck + bundle
```

- The sensor's pcap rule test is skipped unless Suricata is installed (`sudo apt-get install suricata`).
- Contract between sensor and C2 alert models: `.venv-sensor/bin/python scripts/check-ids-contract.py` (run after touching either model).
- Kit and duplicate-file parity: `python3 scripts/check-kit-parity.py`.

### Running a service alone

```bash
# c2 (SQLite, mock backend)
cd services/c2 && DATABASE_URL=sqlite+aiosqlite:///./c2.db DRONE_BACKEND=mock \
  ../../.venv-c2/bin/python -m uvicorn app.main:app --reload --port 8000

# drone (mock)
cd services/drone && DRONE_BACKEND=mock ../../.venv-drone/bin/python -m uvicorn app.main:app --port 9100

# sensor sidecar against any eve.json (Suricata not required)
cd services/sensor && EVE_PATH=/tmp/eve.json ../../.venv-sensor/bin/python -m uvicorn app.main:app --port 9200

# frontend: Vite on :5173 proxying to the C2 (CORS_ORIGINS must include it)
cd services/frontend && npm run dev
```

### Code map

| Path | Content |
|---|---|
| `services/c2/app/services/fleet.py` | Engine: control loop, state machine, claims, broadcast |
| `services/c2/app/dronelink/` | `DroneLink` and adapters |
| `services/c2/app/services/site.py` | Map extent, pads, boundary, routes, inventory; serves `GET /api/site` |
| `services/c2/app/services/ids.py` | Alert relay |
| `services/drone/app/mock/simulator.py` | Mock kinematics |
| `services/drone/app/mavlink/transport.py` | MAVLink 2 surface in front of the mock |
| `services/drone/app/px4/` | Real SITL driver |
| `services/frontend/src` | `pages/` compose, `features/` hold logic in hooks, `components/` presentation, `components/map/` Leaflet |

The mock's WebSocket verb path and its MAVLink surface mutate the same simulator state, so a forged disarm affects the drone the operator is flying. In the frontend, command dispatch belongs in `features/fleet/`, not in components.

### Extending

- **New MAVLink attack:** add the module to `tools/exploit.py` with a help string naming the expected rule class; add the rule, a frame in the pcap fixture and a case in `services/sensor/tests/test_rules_against_pcap.py`.
- **New flight command:** add the verb to `DroneLink`, implement it in both adapters, add the state to `fleet.py`, expose it via `features/fleet/useFleetCommands.ts`.
- **Moving the site or changing routes:** edit `services/c2/app/services/site.py` and `services/c2/app/data/airport_objects.json` (`assets/README.md`). The console draws what the C2 enforces.

### Conventions

- Python: `from __future__ import annotations`, type hints, async throughout.
- TypeScript: strict; the build runs `tsc --noEmit`.
- Secrets are never committed: `.env` is gitignored, `*.example` is not.
