# Getting started

## Prerequisites

- Docker with the Compose v2 plugin.
- PX4 backend: Linux or WSL2 (privileged container, 1 GB shm), about 8 GB RAM, about 20 GB disk. First build compiles firmware (20-40 min).
- Mock backend: any OS, no build.

## Start

```bash
cp env.example .env
docker compose up -d --build                                                      # PX4
docker compose -f docker-compose.yml -f docker-compose.mock.yml up -d --build     # mock, about 2 min
docker compose logs -f drone                                                      # follow the PX4 build
```

| Deployment | Console | API |
|---|---|---|
| docker compose | `http://localhost:8080` (`GCS_HOST_PORT`) | `:8000` (`C2_HOST_PORT`) |
| Ansible | `http://<host>/` (port 80, `drone_lab_console_port`) | `:8000` (`drone_lab_api_port`) |

For Ansible deployment see `ansible/README.md`. For multi-VM see `docs/INFRASTRUCTURE.md`.

## Accounts

The login page does not list them. All three are re-asserted on every boot, so a password change takes effect on the next deploy.

| Account | Variable | Default password | Can |
|---|---|---|---|
| `admin` | `ADMIN_PASSWORD` | `Admin1Admin1` | Everything, including force-releasing another operator's claim |
| `operator` | `OPERATOR_PASSWORD` | `Admin1Admin1` | Claim and fly the drone, read the audit log |
| `observer` | `OBSERVER_PASSWORD` | `Admin1Admin1` | Watch (live mission, Inventory, Network views); command nothing, no audit log |

Usernames: `ADMIN_USERNAME`, `OPERATOR_USERNAME`, `OBSERVER_USERNAME`. `SEED_DEMO_USERS=false` drops the operator and observer. There is no password change in the console.

## First flight

With `AUTO_PATROL=true` (default) the C2 powers the drone on and starts the `perimeter` patrol at 60 m at boot. To fly it yourself: [OPERATOR-GUIDE.md](OPERATOR-GUIDE.md).

Then open the **Network** tab. **Flows** should show C2 to drone traffic at about 20 packets/s (the baseline) and **Alerts** should be empty. Next: [ATTACKS.md](ATTACKS.md).

## Ports

| Port | Component | Purpose |
|---|---|---|
| `8080/tcp` | gcs | Web UI (`80` under Ansible) |
| `8000/tcp` | c2 | REST + WebSocket |
| `9100/tcp` | drone | Lifecycle API, unauthenticated |
| `14550/udp` | drone | MAVLink radio link, unauthenticated |
| `14540/udp` | c2 | MAVLink telemetry relay from the drone |
| `9200/tcp` | sensor | IDS alerts, out of band |
| `5432/tcp` | db | PostgreSQL (internal) |

## Configuration

Environment-driven; see `env.example`.

| Variable | Default | Purpose |
|---|---|---|
| `DRONE_BACKEND` | `px4` | `px4` or `mock` |
| `DRONE_COUNT` | `1` | Fleet size; above 1 shows the swarm UI |
| `HOME_ALT` | `95.0` | Pad elevation. Pad position comes from the site dataset. |
| `JWT_SECRET` | `change-me-to-a-long-random-secret-string` | Deliberately weak |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `720` | Token lifetime |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / `Admin1Admin1` | Admin account |
| `SEED_DEMO_USERS` | `true` | Create operator and observer |
| `OPERATOR_*`, `OBSERVER_*` | `operator` / `observer`, `Admin1Admin1` | Other accounts |
| `AUTO_PATROL`, `AUTO_PATROL_ROUTE`, `AUTO_PATROL_ALT` | `true`, `perimeter`, `60` | Boot onto a patrol |
| `IDS_PUSH_TOKEN` | `ids-dev-token` | Sensor to C2 shared secret |
| `SENSOR_IFACES` | `ot-ops,ot-air` | Suricata capture interfaces |
| `SENSOR_URL` | `http://172.30.10.1:9200` | Where the C2 pulls live traffic |
| `CORS_ORIGINS` | localhost:5173, localhost:8080 | Allowed browser origins |

`AUTO_PATROL*` are C2 settings (`services/c2/app/config.py`) and are not in `env.example`; they reach the C2 only if added to the compose environment.

## Stop and reset

```bash
docker compose down        # keep database and compiled PX4
docker compose down -v     # wipe both volumes
```

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Drone never reaches `READY` | First PX4 boot is a firmware build; watch `docker compose logs -f drone`. Otherwise 30-40 s is normal. `docker compose restart drone`. |
| Host out of disk | Container logs. Compose caps each service at 50 MB x 3. On older checkouts: `sudo truncate -s 0 /var/lib/docker/containers/*/*-json.log`, then `docker compose up -d --force-recreate`. PX4 needs about 7 GB (image plus firmware volume) and about 5 GB transient for the build; `docker builder prune -af` reclaims build cache. |
| Alerts view empty during an attack | `curl -s localhost:9200/health`. `eve_path_exists: false` means Suricata is not writing; check `docker compose logs sensor` and `SENSOR_IFACES`. `ot-ops` / `ot-air` exist only on a single Docker host. |
| Alerts at `:9200` but not in the UI | Push to the C2 failing. Check `IDS_PUSH_TOKEN` matches and `C2_URL` is reachable from the host namespace (the sensor cannot resolve `c2`). |
| Flows view empty | Drone must be powered on. `curl -s localhost:9200/live`; `available: false` means no raw socket (needs `NET_ADMIN`/`NET_RAW` and host networking; rootless Docker will not work). |
| MAVLink attacks connect, nothing happens | Binding instead of dialling, or no heartbeat. From a remote host set `--mavlink-host` and add `--blind`. See `docs/ATTACKS.md`. |
| Drone will not power on | If it was lost outside the area or into a structure, use **Reset Drone**. The terminal logs this at `ERROR` level. |
| Port in use | Change `GCS_HOST_PORT` / `C2_HOST_PORT`, or the published ports in `docker-compose.yml` (`9100`, `14550/udp`, `14540/udp`). |
| Sensor fails to start | Needs `NET_ADMIN`, `NET_RAW` and host networking. |
