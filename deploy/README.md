# deploy/

Per-host compose files for the split (multi-VM) deployment: one component
per file, every cross-host address supplied by `.env` - no compose file
hard-codes a peer. Full architecture, diagrams, and the port matrix are in
[../docs/INFRASTRUCTURE.md](../docs/INFRASTRUCTURE.md).

```bash
cp .env.example .env      # set addresses, credentials, JWT_SECRET, IDS_PUSH_TOKEN

# bring up in order (each on its own host)
docker compose --env-file .env -f db.compose.yml     up -d
docker compose --env-file .env -f drone.compose.yml  up -d --build   # ~20-40 min first boot (PX4)
docker compose --env-file .env -f c2.compose.yml     up -d --build
docker compose --env-file .env -f sensor.compose.yml up -d --build
docker compose --env-file .env -f gcs.compose.yml    up -d --build
```

Boot order matters: `db` must be healthy before `c2` starts (c2 runs
migrations/seeding on boot); `drone` should be reachable before `c2` so its
first lifecycle/MAVLink calls don't fail; `sensor` needs `c2` up to push
alerts; `gcs` only needs `c2`'s REST/WS port reachable.

| File | Host | Segment | Ports | Reaches |
|---|---|---|---|---|
| `db.compose.yml` | db | internal (`ot-ops`) | `5432/tcp` | - |
| `drone.compose.yml` | drone (PX4 SITL) | internal (`ot-air`) | `9100/tcp`, `14550/udp` | `c2:14540/udp` |
| `c2.compose.yml` | c2 | internal (`ot-ops`) | `8000/tcp`, `14540/udp` | `db:5432/tcp`, `drone:9100/tcp` |
| `sensor.compose.yml` | sensor | spans `ot-ops` + `ot-air` (SPAN/mirror, `network_mode: host`) | `9200/tcp` | `c2:8000/tcp` |
| `gcs.compose.yml` | gcs (ground station) | **external / DMZ-adjacent** | `8080/tcp` | `c2:8000/tcp` |

## The one boundary crossing

`gcs` is the only component meant to sit outside the internal/OT network.
Exactly one firewall rule should cross that boundary:

**`gcs` → `c2` on `8000/tcp`** (REST + WebSocket, same port). Nothing else
should be permitted across; `db`, `drone`, and the sensor's direct `9200/tcp`
API stay internal-only (`9200/tcp` is for the blue team / SIEM, reachable
from inside, and is deliberately independent of `c2` so alerts survive a
`c2` compromise - see `docs/MONITORING.md`).

For a mock-backend trial (no PX4 build, no privileged/shm requirements, all
five components on one host), use the all-in-one stack at the repository
root instead:

```bash
docker compose -f ../docker-compose.yml -f ../docker-compose.mock.yml up --build
```
